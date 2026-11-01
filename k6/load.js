import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

// Lecture des deux fichiers de questions (contrat §6, §8 bis et §10) :
// - k6-questions.yaml : 300 questions (100 par équipe : support, rh, dev)
// - reference-questions.yaml : 36 questions de référence (12 par équipe)
const rawQuestionsYaml = open('./k6-questions.yaml');
const rawReferenceYaml = open('./reference-questions.yaml');

function parseYamlScalar(raw) {
  if ((raw.startsWith('"') && raw.endsWith('"')) || (raw.startsWith("'") && raw.endsWith("'"))) {
    try {
      if (raw.startsWith('"')) {
        return JSON.parse(raw);
      }
    } catch (_) {
      // Retirer les guillemets manuellement en repli
    }
    return raw.slice(1, -1);
  }
  return raw;
}

function parseQuestionsList(content) {
  const items = [];
  let current = null;

  const lines = content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (!trimmed || trimmed.startsWith('#') || trimmed === 'questions:') {
      continue;
    }
    if (trimmed.startsWith('- ')) {
      if (current && current.id && current.team && current.question) {
        items.push(current);
      }
      current = { id: '', team: '', question: '' };
      const rest = trimmed.slice(2).trim();
      const idx = rest.indexOf(':');
      if (idx !== -1) {
        const key = rest.slice(0, idx).trim();
        const val = parseYamlScalar(rest.slice(idx + 1).trim());
        if (key === 'id' || key === 'team' || key === 'question') {
          current[key] = val;
        }
      }
    } else if (current) {
      const idx = trimmed.indexOf(':');
      if (idx !== -1) {
        const key = trimmed.slice(0, idx).trim();
        const val = parseYamlScalar(trimmed.slice(idx + 1).trim());
        if (key === 'id' || key === 'team' || key === 'question') {
          current[key] = val;
        }
      }
    }
  }
  if (current && current.id && current.team && current.question) {
    items.push(current);
  }
  return items;
}

const QUESTIONS = parseQuestionsList(rawQuestionsYaml);
const REFERENCE_QUESTIONS = parseQuestionsList(rawReferenceYaml);

if (QUESTIONS.length !== 300) {
  throw new Error(
    `k6-questions.yaml doit contenir exactement 300 questions (lu : ${QUESTIONS.length})`
  );
}
if (REFERENCE_QUESTIONS.length !== 36) {
  throw new Error(
    `reference-questions.yaml doit contenir exactement 36 questions de référence (lu : ${REFERENCE_QUESTIONS.length})`
  );
}

const TEAMS = ['support', 'rh', 'dev'];
const QUESTIONS_BY_TEAM = {
  support: QUESTIONS.filter((q) => q.team === 'support'),
  rh: QUESTIONS.filter((q) => q.team === 'rh'),
  dev: QUESTIONS.filter((q) => q.team === 'dev'),
};

// Formule du cycle de charge (période de 3 600 s ancrée sur l'heure Unix) :
// lambda(t) = 0.5 + 0.1 * sin(2 * pi * (t mod 3600) / 3600) req/s
export function computeLambdaReqPerSec(unixSeconds) {
  const phase = ((unixSeconds % 3600) + 3600) % 3600;
  return 0.5 + 0.1 * Math.sin((2 * Math.PI * phase) / 3600.0);
}

export function buildDiurnalStages(nowUnixSeconds, numMinutes, stepSeconds) {
  const stages = [];
  for (let i = 1; i <= numMinutes; i++) {
    const t = nowUnixSeconds + i * stepSeconds;
    const ratePerMin = Math.round(computeLambdaReqPerSec(t) * 60);
    stages.push({
      duration: `${stepSeconds}s`,
      target: ratePerMin,
    });
  }
  return stages;
}

const nowUnixSeconds = __ENV.K6_FIXED_UNIX_TS
  ? parseInt(__ENV.K6_FIXED_UNIX_TS, 10)
  : Math.floor(Date.now() / 1000);

const stepSeconds = __ENV.K6_STAGE_STEP_SECONDS
  ? parseInt(__ENV.K6_STAGE_STEP_SECONDS, 10)
  : 60;

const numSteps = __ENV.K6_STAGE_COUNT
  ? parseInt(__ENV.K6_STAGE_COUNT, 10)
  : 180;

const initialRatePerMin = Math.round(computeLambdaReqPerSec(nowUnixSeconds) * 60);

export const options = {
  insecureSkipTLSVerify: true,
  scenarios: {
    orion_diurnal_cycle: {
      executor: 'ramping-arrival-rate',
      startRate: initialRatePerMin,
      timeUnit: '1m',
      preAllocatedVUs: 12,
      maxVUs: 40,
      stages: buildDiurnalStages(nowUnixSeconds, numSteps, stepSeconds),
    },
  },
};

const BASE_URL = (__ENV.ORION_BASE_URL || 'https://traefik').replace(/\/$/, '');
const SEED = parseInt(__ENV.K6_SEED || '42', 10);

const TEAM_KEYS = {
  support: __ENV.ORION_KEY_SUPPORT || '',
  rh: __ENV.ORION_KEY_RH || '',
  dev: __ENV.ORION_KEY_DEV || '',
};

// Générateur pseudo-aléatoire déterministe (Mulberry32)
function seededIndex(seed, step, length) {
  let t = (seed + step * 0x6d2b79f5) | 0;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  const u = ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  return Math.floor(u * length);
}

export default function () {
  const iter = exec.scenario.iterationInTest;
  // Débit moyen de 30 req/min : 1 question sur 30 est une question de référence (~1/min)
  const isReference = iter % 30 === 0;

  let item;
  if (isReference) {
    // Parcourt toutes les questions de référence de manière déterministe
    const refStep = Math.floor(iter / 30);
    const idx = (SEED + refStep) % REFERENCE_QUESTIONS.length;
    item = REFERENCE_QUESTIONS[idx];
  } else {
    const teamName = TEAMS[iter % 3];
    const teamPool = QUESTIONS_BY_TEAM[teamName];
    const idx = seededIndex(SEED, iter, teamPool.length);
    item = teamPool[idx];
  }

  const team = item.team || 'support';
  const apiKey = TEAM_KEYS[team] || TEAM_KEYS.support;

  const headers = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${apiKey}`,
  };
  if (isReference) {
    headers['X-Orion-Synthetic'] = '1';
  }

  const payload = JSON.stringify({
    question: item.question,
  });

  const res = http.post(`${BASE_URL}/ask`, payload, {
    headers,
    timeout: '45s',
    tags: {
      team,
      reference: isReference ? 'true' : 'false',
    },
  });

  check(res, {
    'statut HTTP reçu': (r) => r.status > 0,
  });
}
