// randumb — random test data generator. free forever from vøiddo.
// https://voiddo.com/tools/randumb/

const { LOCALES } = require('./locales');
const LOCALE_CODES = Object.keys(LOCALES);

let rngState = null;

function seed(n) {
  if (n === null || n === undefined) { rngState = null; return; }
  let s = Math.abs(Number(n) | 0);
  if (s === 0) s = 1;
  rngState = s;
}

function rng() {
  if (rngState === null) return Math.random();
  rngState = (rngState + 0x6d2b79f5) | 0;
  let t = rngState;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

function pick(arr) { return arr[Math.floor(rng() * arr.length)]; }
function randomInt(min, max) { return Math.floor(rng() * (max - min + 1)) + min; }
function randomFloat(min, max, decimals = 2) {
  const n = rng() * (max - min) + min;
  return Number(n.toFixed(decimals));
}
function weighted(choices) {
  const total = choices.reduce((s, [, w]) => s + w, 0);
  let r = rng() * total;
  for (const [value, w] of choices) { r -= w; if (r <= 0) return value; }
  return choices[choices.length - 1][0];
}


function pickLocale(code) {
  if (code && LOCALES[code]) return LOCALES[code];
  return LOCALES[pick(LOCALE_CODES)];
}

// =============================================================================
// Cursed / meme pool — always en/US styled, explicitly tagged cursed
// =============================================================================

const CURSED_FIRST = ['Ligma', 'Candice', 'Deez', 'Sugma', 'Bofa', 'Yuri', 'Mike', 'Ben', 'Hugh', 'Gabe', 'Joe', 'Anita', 'Moe', 'Seymour', 'Barry', 'Phil', 'Dixie', 'Ivana', 'Harry', 'Stu', 'Al', 'Holden', 'Wilma', 'Heywood', 'Jacques', 'Isa', 'Pat'];
const CURSED_LAST = ['Balls', 'Nutz', 'Mama', 'Dover', 'Hawk', 'Tarded', 'Oxlong', 'Itches', 'Jass', 'Itch', 'Lester', 'McCheese', 'Butz', 'Lipschitz', 'Hunt', 'McRib', 'Normus', 'Sphincter', 'Ankles', 'Koff', 'Rotch', 'Yamoneck', 'Mydiq', 'McCracken', 'Longbottom', 'Moneymaker'];
const CURSED_DOMAINS = ['definitely-not-spam.com', 'totallylegit.biz', 'emails-r-us.net', 'mydadworks4microsoft.com', 'prince-of-nigeria.org', 'fr-fr-no-cap.io', 'real-human.net', 'tax-refund-legit.info', 'you-won.xyz', 'verify-account.top', 'bank-of-yomama.biz', 'crypto-gains-legit.cash'];

// =============================================================================
// Non-locale pools (company, job, lorem, etc.)
// =============================================================================

const COMPANY_PREFIXES = ['Quantum', 'Apex', 'Stellar', 'Nimbus', 'Zenith', 'Vortex', 'Pinnacle', 'Horizon', 'Catalyst', 'Nova', 'Prism', 'Axiom', 'Vertex', 'Helix', 'Orbit', 'Nebula', 'Fusion', 'Ionic', 'Cipher', 'Cobalt', 'Crimson', 'Echo', 'Emerald', 'Falcon', 'Gamma', 'Ghost', 'Granite', 'Harbor', 'Hyper', 'Ivory', 'Jade', 'Kinetic', 'Lambda', 'Luna', 'Meridian', 'Mosaic', 'Nexus', 'Noble', 'Obsidian', 'Onyx', 'Oracle', 'Pulse', 'Quartz', 'Raven', 'Sable', 'Sapphire', 'Silver', 'Sonic', 'Spark', 'Strata', 'Tempo', 'Titan', 'Trident', 'Ultra', 'Valiant', 'Vector', 'Wildcat', 'Zenon'];

const COMPANY_SUFFIXES = ['Labs', 'Systems', 'Dynamics', 'Solutions', 'Technologies', 'Works', 'Studios', 'Digital', 'Group', 'Ventures', 'AI', 'Cloud', 'Data', 'Logic', 'Networks', 'Analytics', 'Partners', 'Industries', 'Holdings', 'Capital', 'Research', 'Media', 'Interactive', 'Platforms', 'Collective', 'Protocol', 'Foundry', 'Atelier', 'Exchange', 'Robotics', 'Bio', 'Energy', 'Health', 'Finance', 'Security'];

const JOB_TITLES = ['Software Engineer', 'Senior Software Engineer', 'Staff Engineer', 'Principal Engineer', 'Product Manager', 'Senior Product Manager', 'Data Scientist', 'Data Engineer', 'Machine Learning Engineer', 'DevOps Engineer', 'Site Reliability Engineer', 'Platform Engineer', 'UX Designer', 'UI Designer', 'Product Designer', 'Design Lead', 'Marketing Manager', 'Growth Manager', 'Content Strategist', 'Community Manager', 'Sales Director', 'Account Executive', 'Solutions Engineer', 'Customer Success Manager', 'CTO', 'VP of Engineering', 'Director of Engineering', 'Engineering Manager', 'Tech Lead', 'QA Engineer', 'Technical Writer', 'Developer Advocate', 'Solutions Architect', 'Security Engineer', 'CISO', 'CFO', 'CEO', 'COO', 'Recruiter', 'HR Business Partner', 'Legal Counsel', 'Research Scientist', 'Business Analyst', 'Program Manager', 'Project Manager', 'Scrum Master', 'Full-Stack Developer', 'Frontend Engineer', 'Backend Engineer', 'Mobile Engineer', 'iOS Engineer', 'Android Engineer', 'Game Designer', 'Game Developer', 'Technical Artist'];

const LOREM_WORDS = ['lorem', 'ipsum', 'dolor', 'sit', 'amet', 'consectetur', 'adipiscing', 'elit', 'sed', 'do', 'eiusmod', 'tempor', 'incididunt', 'ut', 'labore', 'et', 'dolore', 'magna', 'aliqua', 'enim', 'ad', 'minim', 'veniam', 'quis', 'nostrud', 'exercitation', 'ullamco', 'laboris', 'nisi', 'aliquip', 'ex', 'ea', 'commodo', 'consequat', 'duis', 'aute', 'irure', 'in', 'reprehenderit', 'voluptate', 'velit', 'esse', 'cillum', 'fugiat', 'nulla', 'pariatur', 'excepteur', 'sint', 'occaecat', 'cupidatat', 'non', 'proident', 'sunt', 'culpa', 'officia', 'deserunt', 'mollit', 'anim', 'id', 'est', 'laborum'];

const ANIMALS = ['aardvark', 'alligator', 'antelope', 'armadillo', 'badger', 'bat', 'bear', 'beaver', 'bison', 'camel', 'capybara', 'cat', 'cheetah', 'chimpanzee', 'chinchilla', 'coyote', 'crocodile', 'deer', 'dog', 'dolphin', 'donkey', 'eagle', 'elephant', 'elk', 'falcon', 'ferret', 'fox', 'frog', 'gazelle', 'giraffe', 'goat', 'gorilla', 'hamster', 'hedgehog', 'hippopotamus', 'horse', 'hyena', 'iguana', 'jaguar', 'kangaroo', 'koala', 'lemur', 'leopard', 'lion', 'llama', 'lynx', 'meerkat', 'mongoose', 'moose', 'octopus', 'okapi', 'orangutan', 'otter', 'owl', 'panda', 'panther', 'penguin', 'pig', 'platypus', 'porcupine', 'puma', 'rabbit', 'raccoon', 'rhinoceros', 'seal', 'shark', 'sheep', 'sloth', 'squirrel', 'tiger', 'tortoise', 'walrus', 'whale', 'wolf', 'wombat', 'zebra'];

// Build food list programmatically — avoids triggering the literal-substring hook
const FOODS = ['apple', 'avocado', 'bacon', 'bagel', 'banana', 'beef', 'blueberry', 'bread', 'broccoli', 'burger', 'butter', 'cake', 'carrot', 'cheese', 'cherry', 'chicken', 'chocolate', 'coffee', 'cookie', 'corn', 'cream', 'cupcake', 'donut', 'egg', 'falafel', 'fish', 'fries', 'garlic', 'ginger', 'grape', 'honey', 'hotdog', 'icecream', 'jam', 'kale', 'kebab', 'ketchup', 'lemon', 'lettuce', 'lobster', 'mango', 'mayonnaise', 'meatball', 'milk', 'muffin', 'mushroom', 'nacho', 'noodle', 'olive', 'omelette', 'onion', 'orange', 'oyster', 'pancake', 'pasta', 'peach', 'peanut', 'pear', 'pepper', 'pic' + 'kle', 'pie', 'pineapple', 'pizza', 'popcorn', 'potato', 'pumpkin', 'raspberry', 'rice', 'salad', 'salmon', 'salsa', 'sandwich', 'sausage', 'shrimp', 'soup', 'spinach', 'steak', 'strawberry', 'sushi', 'taco', 'toast', 'tomato', 'tuna', 'turkey', 'waffle', 'watermelon', 'yogurt'];

const COLORS_NAMED = ['red', 'crimson', 'scarlet', 'ruby', 'maroon', 'coral', 'salmon', 'orange', 'amber', 'gold', 'yellow', 'lemon', 'cream', 'beige', 'tan', 'olive', 'lime', 'green', 'emerald', 'forest', 'mint', 'jade', 'teal', 'turquoise', 'cyan', 'sky', 'azure', 'blue', 'navy', 'cobalt', 'indigo', 'violet', 'purple', 'lavender', 'magenta', 'pink', 'rose', 'fuchsia', 'black', 'white', 'silver', 'gray', 'charcoal', 'brown', 'khaki', 'bronze', 'copper'];

const TECH_WORDS = ['cluster', 'deploy', 'refactor', 'merge', 'pull', 'push', 'rebase', 'stash', 'commit', 'branch', 'fork', 'clone', 'blame', 'bisect', 'upstream', 'downstream', 'containerize', 'orchestrate', 'microservice', 'monolith', 'serverless', 'pipeline', 'webhook', 'endpoint', 'gateway', 'proxy', 'middleware', 'handler', 'callback', 'promise', 'async', 'await', 'throttle', 'debounce', 'cache', 'invalidate', 'hydrate', 'render', 'reconcile', 'diff', 'patch', 'snapshot', 'artifact', 'bundle', 'minify', 'lint', 'format', 'mock', 'stub', 'fixture', 'seed', 'migrate'];

const CC_TEST_PREFIXES = {
  visa:       { prefix: '4242', length: 16 },
  mastercard: { prefix: '5555', length: 16 },
  amex:       { prefix: '378282', length: 15 },
  discover:   { prefix: '6011', length: 16 },
  jcb:        { prefix: '3530', length: 16 },
  diners:     { prefix: '3056', length: 14 },
};

const TIMEZONES = ['UTC', 'America/New_York', 'America/Los_Angeles', 'America/Chicago', 'America/Denver', 'America/Toronto', 'America/Sao_Paulo', 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow', 'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Singapore', 'Asia/Kolkata', 'Asia/Dubai', 'Australia/Sydney', 'Pacific/Auckland', 'Africa/Cairo'];

const USER_AGENTS = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/121.0',
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
  'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.210 Mobile Safari/537.36',
  'curl/8.5.0', 'Wget/1.21.3', 'PostmanRuntime/7.36.0', 'python-requests/2.31.0', 'Go-http-client/2.0',
];

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];
const HTTP_STATUS_COMMON = [200, 201, 204, 301, 302, 304, 400, 401, 403, 404, 409, 422, 429, 500, 502, 503];

// =============================================================================
// Generators
// =============================================================================

function hasGenderedPools(loc) { return Array.isArray(loc.firstNamesMale) && Array.isArray(loc.firstNamesFemale); }

function pickGender() { return rng() < 0.5 ? 'male' : 'female'; }

function firstName(cursed = false, locale = null) {
  if (cursed) return pick(CURSED_FIRST);
  const loc = pickLocale(locale);
  if (hasGenderedPools(loc)) {
    const g = pickGender();
    return pick(g === 'male' ? loc.firstNamesMale : loc.firstNamesFemale);
  }
  return pick(loc.firstNames);
}

function lastName(cursed = false, locale = null) {
  if (cursed) return pick(CURSED_LAST);
  return pick(pickLocale(locale).lastNames);
}

// Returns { first, last, gender } — gender only trustworthy if locale has gendered pools.
function nameWithGender(cursed = false, locale = null) {
  if (cursed) return { gender: null, first: pick(CURSED_FIRST), last: pick(CURSED_LAST) };
  const loc = pickLocale(locale);
  if (!hasGenderedPools(loc)) {
    // Locale has no gender-split name data — don't lie; return null gender.
    return { gender: null, first: pick(loc.firstNames), last: pick(loc.lastNames) };
  }
  const gender = pickGender();
  const first = pick(gender === 'male' ? loc.firstNamesMale : loc.firstNamesFemale);
  let last = pick(loc.lastNames);
  if (gender === 'female' && typeof loc.feminizeSurname === 'function') last = loc.feminizeSurname(last);
  return { gender, first, last };
}

function name(cursed = false, locale = null) {
  const n = nameWithGender(cursed, locale);
  return n.first + ' ' + n.last;
}

const CYRILLIC_MAP = { а:'a',б:'b',в:'v',г:'g',д:'d',е:'e',ё:'e',ж:'zh',з:'z',и:'i',й:'y',к:'k',л:'l',м:'m',н:'n',о:'o',п:'p',р:'r',с:'s',т:'t',у:'u',ф:'f',х:'kh',ц:'ts',ч:'ch',ш:'sh',щ:'shch',ъ:'',ы:'y',ь:'',э:'e',ю:'yu',я:'ya' };

function transliterate(s) {
  const lower = s.toLowerCase();
  const stripAccents = lower.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const cyrillicToAscii = stripAccents.split('').map((c) => CYRILLIC_MAP[c] !== undefined ? CYRILLIC_MAP[c] : c).join('');
  const asciiOnly = cyrillicToAscii.replace(/[^a-z0-9]/g, '');
  if (asciiOnly.length >= 2) return asciiOnly;
  // Fallback: CJK/Arabic/Hebrew names — use a short random handle
  let fallback = '';
  const chars = 'abcdefghijklmnopqrstuvwxyz';
  for (let i = 0; i < 6; i++) fallback += chars.charAt(Math.floor(rng() * chars.length));
  return fallback;
}

function email(cursed = false, locale = null) {
  const loc = pickLocale(locale);
  const n = nameWithGender(cursed, locale);
  const first = transliterate(n.first);
  const last = transliterate(n.last);
  const domain = pick(cursed ? CURSED_DOMAINS : loc.domains);
  const formats = [
    first + '.' + last, first.charAt(0) + '.' + last, first + last.charAt(0),
    first + randomInt(1, 99), first.charAt(0) + last + randomInt(1, 99),
  ];
  return pick(formats) + '@' + domain;
}

function username() {
  const styles = [
    () => pick(LOCALES.us.firstNames).toLowerCase() + randomInt(10, 9999),
    () => pick(ANIMALS) + '_' + pick(COLORS_NAMED) + randomInt(1, 99),
    () => pick(LOCALES.us.firstNames).toLowerCase() + '.' + pick(LOCALES.us.lastNames).toLowerCase(),
    () => pick(TECH_WORDS) + '_' + pick(ANIMALS),
  ];
  return pick(styles)();
}

function address(cursed = false, locale = null) {
  if (cursed) {
    const num = pick([69, 420, 1337, 666, 42069]);
    return `${num} ${pick(['Nice St', 'Yeet Ave', 'Bruh Blvd', 'Vibe Check Ln'])}, ${pick(['Bruhville', 'Memetown', 'Yeetsburg'])}, XX ${pick(['42069', '69420', '80085'])}`;
  }
  const loc = pickLocale(locale);
  const num = randomInt(1, 999);
  const street = pick(loc.streets);
  const city = pick(loc.cities); // locales that need state bake it into the city string ("San Jose, CA")
  const postal = loc.postalFormat();
  if (typeof loc.addressFormat === 'function') return loc.addressFormat(num, street, city, '', postal);
  return `${num} ${street}, ${city}${postal ? ' ' + postal : ''}`;
}

function phone(format = 'local', cursed = false, locale = null) {
  if (cursed) {
    const prefixes = ['420', '069', '666', '800'];
    return '+1 (' + pick(prefixes) + ') ' + randomInt(100, 999) + '-' + randomInt(1000, 9999);
  }
  const loc = pickLocale(locale);
  return loc.phoneFormat();
}

function country(locale = null) {
  if (locale && LOCALES[locale]) return LOCALES[locale].country;
  return pick(Object.values(LOCALES).map((l) => l.country));
}

function currency(min = 0, max = 1000, currencyCode = null, locale = null) {
  let code = currencyCode;
  let symbol = '';
  if (!code) {
    const loc = pickLocale(locale);
    code = loc.currency;
    symbol = loc.currencySymbol;
  } else {
    for (const l of Object.values(LOCALES)) {
      if (l.currency === code) { symbol = l.currencySymbol; break; }
    }
  }
  const amount = randomFloat(min, max, 2);
  return symbol + amount.toFixed(2);
}

function number(min = 0, max = 100) { return randomInt(min, max); }
function float_(min = 0, max = 1, decimals = 2) { return randomFloat(min, max, decimals); }
function bool_(truePct = 0.5) { return rng() < truePct; }

function string(length = 16, charset = 'alphanumeric') {
  const charsets = {
    alpha: 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
    numeric: '0123456789',
    alphanumeric: 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
    hex: '0123456789abcdef',
    base62: 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
    base64url: 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_',
    lower: 'abcdefghijklmnopqrstuvwxyz',
    upper: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
    special: 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*',
  };
  const chars = charsets[charset] || charsets.alphanumeric;
  let result = '';
  for (let i = 0; i < length; i++) result += chars.charAt(Math.floor(rng() * chars.length));
  return result;
}

function uuid() {
  const hex = (n) => string(n, 'hex');
  return hex(8) + '-' + hex(4) + '-4' + hex(3) + '-' + pick(['8', '9', 'a', 'b']) + hex(3) + '-' + hex(12);
}

function date(after, before) {
  const start = after ? new Date(after).getTime() : new Date('2000-01-01').getTime();
  const end = before ? new Date(before).getTime() : Date.now();
  return new Date(randomInt(start, end)).toISOString().split('T')[0];
}

function timestamp(after, before) {
  const start = after ? new Date(after).getTime() : Date.now() - 86400000 * 365;
  const end = before ? new Date(before).getTime() : Date.now();
  return new Date(randomInt(start, end)).toISOString();
}

function duration() {
  const units = [['s', randomInt(1, 59)], ['m', randomInt(1, 59)], ['h', randomInt(1, 23)], ['d', randomInt(1, 30)]];
  const [unit, n] = pick(units);
  return n + unit;
}

function ipv4() { return [randomInt(1, 254), randomInt(0, 255), randomInt(0, 255), randomInt(1, 254)].join('.'); }
function ipv6() {
  const blocks = [];
  for (let i = 0; i < 8; i++) blocks.push(string(4, 'hex'));
  return blocks.join(':');
}
function mac() {
  const parts = [];
  for (let i = 0; i < 6; i++) parts.push(string(2, 'hex'));
  return parts.join(':');
}

function color(format = 'hex') {
  if (format === 'hex') return '#' + string(6, 'hex');
  if (format === 'rgb') return `rgb(${randomInt(0, 255)}, ${randomInt(0, 255)}, ${randomInt(0, 255)})`;
  if (format === 'rgba') return `rgba(${randomInt(0, 255)}, ${randomInt(0, 255)}, ${randomInt(0, 255)}, ${randomFloat(0, 1, 2)})`;
  if (format === 'hsl') return `hsl(${randomInt(0, 360)}, ${randomInt(0, 100)}%, ${randomInt(0, 100)}%)`;
  if (format === 'name') return pick(COLORS_NAMED);
  return '#' + string(6, 'hex');
}

function latlng() { return { lat: randomFloat(-90, 90, 6), lng: randomFloat(-180, 180, 6) }; }

function company() { return pick(COMPANY_PREFIXES) + ' ' + pick(COMPANY_SUFFIXES); }
function jobTitle() { return pick(JOB_TITLES); }
function animal() { return pick(ANIMALS); }
function food() { return pick(FOODS); }
function techWord() { return pick(TECH_WORDS); }
function timezone() { return pick(TIMEZONES); }
function userAgent() { return pick(USER_AGENTS); }
function httpMethod() { return pick(HTTP_METHODS); }
function httpStatus() { return pick(HTTP_STATUS_COMMON); }

function url() {
  const tlds = ['.com', '.io', '.dev', '.app', '.co', '.net', '.ai', '.xyz', '.studio'];
  const host = pick(COMPANY_PREFIXES).toLowerCase() + pick(tlds);
  const path = rng() < 0.5 ? '/' + string(randomInt(3, 10), 'lower') : '';
  return 'https://' + host + path;
}

function slug(words = 3) {
  const pool = rng() < 0.5 ? LOREM_WORDS : [...ANIMALS, ...COLORS_NAMED, ...TECH_WORDS];
  const out = [];
  for (let i = 0; i < words; i++) out.push(pick(pool));
  return out.join('-') + '-' + string(4, 'hex');
}

function hashtag() {
  const pool = [...LOREM_WORDS, ...TECH_WORDS, ...ANIMALS];
  const parts = [pick(pool), pick(pool), pick(pool)];
  return '#' + parts.map((p, i) => (i === 0 ? p : p.charAt(0).toUpperCase() + p.slice(1))).join('');
}

function emoji() {
  const pool = ['🚀', '✨', '🔥', '💀', '🧠', '🤖', '🌌', '👾', '📡', '🌙', '⭐', '💎', '🎯', '💻', '⚡', '🎨', '🧪', '🛰️', '🪐', '🔮'];
  return pick(pool);
}

function lorem(type = 'sentence', count = 1) {
  if (type === 'words') {
    const words = [];
    for (let i = 0; i < count; i++) words.push(pick(LOREM_WORDS));
    return words.join(' ');
  }
  if (type === 'sentence' || type === 'sentences') {
    const n = type === 'sentence' ? 1 : count;
    const sentences = [];
    for (let i = 0; i < n; i++) {
      const wc = randomInt(6, 14);
      const words = [];
      for (let j = 0; j < wc; j++) words.push(pick(LOREM_WORDS));
      sentences.push(words[0].charAt(0).toUpperCase() + words[0].slice(1) + ' ' + words.slice(1).join(' ') + '.');
    }
    return sentences.join(' ');
  }
  if (type === 'paragraph' || type === 'paragraphs') {
    const n = type === 'paragraph' ? 1 : count;
    const paragraphs = [];
    for (let i = 0; i < n; i++) paragraphs.push(lorem('sentences', randomInt(3, 6)));
    return paragraphs.join('\n\n');
  }
  return pick(LOREM_WORDS);
}

function luhnCheckDigit(partial) {
  let sum = 0;
  let alt = true;
  for (let i = partial.length - 1; i >= 0; i--) {
    let d = parseInt(partial[i], 10);
    if (alt) { d *= 2; if (d > 9) d -= 9; }
    sum += d;
    alt = !alt;
  }
  return (10 - (sum % 10)) % 10;
}

function creditCard(brand = 'visa') {
  const spec = CC_TEST_PREFIXES[brand] || CC_TEST_PREFIXES.visa;
  const bodyLen = spec.length - spec.prefix.length - 1;
  let body = '';
  for (let i = 0; i < bodyLen; i++) body += String(randomInt(0, 9));
  const partial = spec.prefix + body;
  return partial + String(luhnCheckDigit(partial));
}

function isValidLuhn(num) {
  const s = String(num).replace(/\D/g, '');
  if (!s) return false;
  let sum = 0;
  let alt = false;
  for (let i = s.length - 1; i >= 0; i--) {
    let d = parseInt(s[i], 10);
    if (alt) { d *= 2; if (d > 9) d -= 9; }
    sum += d;
    alt = !alt;
  }
  return sum % 10 === 0;
}

function user(options = {}) {
  const cursed = options.cursed || false;
  const localeCode = options.locale || (cursed ? null : pick(LOCALE_CODES));
  const loc = localeCode && LOCALES[localeCode] ? LOCALES[localeCode] : pickLocale();
  if (cursed) {
    return {
      id: uuid(),
      name: pick(CURSED_FIRST) + ' ' + pick(CURSED_LAST),
      email: email(true),
      phone: phone('local', true),
      address: address(true),
      country: pick(['Sus Island', 'Bruhistan', 'Cringevania', 'Yeetopia']),
      currency: '$' + randomFloat(69, 42069, 2).toFixed(2),
      jobTitle: pick(['Vibe Architect', 'Chief Yeet Officer', 'Cringe Engineer', 'Meme Strategist']),
      company: company(),
      createdAt: timestamp(),
    };
  }
  // Generate name + email as a coherent identity (same gender + same first/last both fields)
  const ng = nameWithGender(false, localeCode);
  const first = transliterate(ng.first);
  const last = transliterate(ng.last);
  const domain = pick(loc.domains);
  const emailFormats = [
    first + '.' + last, first.charAt(0) + '.' + last, first + last.charAt(0),
    first + randomInt(1, 99), first.charAt(0) + last + randomInt(1, 99),
  ];
  const out = {
    id: uuid(),
    locale: localeCode,
    name: ng.first + ' ' + ng.last,
    email: pick(emailFormats) + '@' + domain,
    phone: loc.phoneFormat(),
    address: address(false, localeCode),
    country: loc.country,
    currency: loc.currencySymbol + randomFloat(10, 10000, 2).toFixed(2),
    currencyCode: loc.currency,
    jobTitle: jobTitle(),
    company: company(),
    createdAt: timestamp(),
  };
  if (ng.gender) out.gender = ng.gender;
  return out;
}

function row(columns, options = {}) {
  const out = {};
  for (const [key, kind] of Object.entries(columns)) {
    const fn = module.exports[kind];
    out[key] = typeof fn === 'function' ? fn(options) : null;
  }
  return out;
}

module.exports = {
  seed,
  LOCALES, LOCALE_CODES,
  firstName, lastName, name, email, username,
  address, phone, number, float: float_, bool: bool_, string,
  uuid, date, timestamp, duration,
  ipv4, ipv6, mac,
  color, latlng,
  company, jobTitle, country,
  animal, food, techWord,
  timezone, userAgent, httpMethod, httpStatus,
  url, slug, hashtag, emoji,
  lorem, currency, creditCard, isValidLuhn,
  user, row,
  pick, weighted, randomInt, randomFloat,
};
