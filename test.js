// randumb — tests. free forever from vøiddo. https://voiddo.com/tools/randumb/

const g = require('./src/generator');

let passed = 0;
let failed = 0;

function test(name, condition, detail) {
  if (condition) { console.log('\x1b[32m✓ ' + name + '\x1b[0m'); passed++; }
  else { console.log('\x1b[31m✗ ' + name + '\x1b[0m'); if (detail !== undefined) console.log('  got: ' + JSON.stringify(detail)); failed++; }
}

// Primitives
test('uuid has 36 chars', g.uuid().length === 36);
test('uuid has v4 marker', /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(g.uuid()));
test('ipv4 valid', /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(g.ipv4()));
test('ipv6 valid shape', /^([0-9a-f]{4}:){7}[0-9a-f]{4}$/.test(g.ipv6()));
test('mac valid', /^([0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(g.mac()));
test('color hex starts with #', g.color('hex').startsWith('#'));
test('number in range', (() => { for (let i=0;i<100;i++){ const n=g.number(5,10); if (n<5||n>10) return false; } return true; })());
test('bool returns boolean', typeof g.bool() === 'boolean');

// Seeded determinism
g.seed(42); const a1 = g.uuid(); const a2 = g.uuid();
g.seed(42); const b1 = g.uuid(); const b2 = g.uuid();
g.seed(null);
test('seeded output is deterministic', a1 === b1 && a2 === b2, { a1, b1 });

// Luhn credit cards
for (const brand of ['visa','mastercard','amex','discover','jcb','diners']) {
  const cc = g.creditCard(brand);
  test(`creditCard(${brand}) is Luhn-valid`, g.isValidLuhn(cc), cc);
}

// Lorem
test('lorem sentence ends with period', g.lorem('sentence').endsWith('.'));
test('lorem paragraphs returns 3 chunks', g.lorem('paragraphs', 3).split('\n\n').length === 3);

// Locales
test('has 55+ locales', Object.keys(g.LOCALES).length >= 55, Object.keys(g.LOCALES).length);
test('US has 1000+ first names', g.LOCALES.us.firstNames.length >= 1000, g.LOCALES.us.firstNames.length);
test('US has 500+ last names', g.LOCALES.us.lastNames.length >= 500, g.LOCALES.us.lastNames.length);

// Locale coupling
const ruUser = g.user({ locale: 'ru' });
test('RU user has Russia as country', ruUser.country === 'Russia');
test('RU user phone starts with +7', ruUser.phone.startsWith('+7'), ruUser.phone);
test('RU user currency is RUB', ruUser.currencyCode === 'RUB');
test('RU user has gender tag (male/female)', ['male','female'].includes(ruUser.gender), ruUser);

// RU female surname feminization
g.seed(100);
let foundFemRU = null;
for (let i = 0; i < 50 && !foundFemRU; i++) { const u = g.user({ locale: 'ru' }); if (u.gender === 'female') foundFemRU = u; }
g.seed(null);
test('RU female surname ends in -a/-aya/-skaya', foundFemRU && /(a|aya|skaya)$/.test(foundFemRU.name), foundFemRU);

// MD user distinct from RU (Moldova is Romanian-speaking)
const mdUser = g.user({ locale: 'md' });
test('MD user has Moldova as country', mdUser.country === 'Moldova');
test('MD user phone starts with +373', mdUser.phone.startsWith('+373'));
test('MD user currency is MDL', mdUser.currencyCode === 'MDL');

// IL uses shekel, +972, Latin Israeli names
const ilUser = g.user({ locale: 'il' });
test('IL user has Israel as country', ilUser.country === 'Israel');
test('IL user phone starts with +972', ilUser.phone.startsWith('+972'));
test('IL user currency is ILS', ilUser.currencyCode === 'ILS');
test('IL user name is Latin ASCII', /^[A-Za-z\- ']+$/.test(ilUser.name), ilUser.name);

// JP: transliterated names in Latin
const jpUser = g.user({ locale: 'jp' });
test('JP user has Japan as country', jpUser.country === 'Japan');
test('JP user name is Latin ASCII', /^[A-Za-z\- ']+$/.test(jpUser.name), jpUser.name);

// No Cyrillic/Hebrew/Arabic/CJK leaks
const codes = Object.keys(g.LOCALES);
const multiSample = Array.from({length: 200}, (_, i) => g.user({ locale: codes[i % codes.length] }));
const nonLatinRe = /[\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u3040-\u30FF\u4E00-\u9FFF\u0980-\u09FF\u0E00-\u0E7F]/;
const offender = multiSample.find((u) => nonLatinRe.test(u.name + u.email + u.address + u.country));
test('no non-Latin scripts in any user field', !offender, offender || null);

// User ID structure
const u = g.user({ locale: 'us' });
test('US user has all required fields', ['id','name','email','phone','address','country','currency','jobTitle','company','createdAt'].every((k) => u[k] !== undefined));

// Weighted
g.seed(1);
const wc = { a: 0, b: 0, c: 0 };
for (let i = 0; i < 1000; i++) wc[g.weighted([['a', 10], ['b', 1], ['c', 1]])]++;
g.seed(null);
test('weighted respects weights', wc.a > wc.b * 3 && wc.a > wc.c * 3, wc);

console.log('\n' + passed + '/' + (passed + failed) + ' tests passed\n');
if (failed > 0) process.exit(1);
