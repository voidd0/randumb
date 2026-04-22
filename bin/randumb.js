#!/usr/bin/env node
// randumb — random test data generator. free forever from vøiddo.
// https://voiddo.com/tools/randumb/

const generator = require('../src/generator');

const YELLOW = '\x1b[33m';
const CYAN = '\x1b[36m';
const GREEN = '\x1b[32m';
const DIM = '\x1b[2m';
const BOLD = '\x1b[1m';
const RESET = '\x1b[0m';

const args = process.argv.slice(2);
const command = args[0];

function getArg(names, defaultVal = null) {
  for (const name of names) {
    const idx = args.indexOf(name);
    if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  }
  return defaultVal;
}

function hasFlag(names) { return names.some((n) => args.includes(n)); }

function readPkgVersion() {
  try { return require('../package.json').version; } catch { return 'unknown'; }
}

function showHelp() {
  const localeList = Object.keys(generator.LOCALES).join(', ');
  console.log(`
${BOLD}${YELLOW}randumb${RESET} ${DIM}v${readPkgVersion()}${RESET}
${DIM}// locale-consistent random test data. free forever from vøiddo.${RESET}

${CYAN}Usage${RESET}
  randumb <command> [options]

${CYAN}Commands${RESET}
  ${BOLD}Identity${RESET}     name, firstname, lastname, email, username, user
  ${BOLD}Contact${RESET}      address, phone, country
  ${BOLD}IDs${RESET}          uuid, ipv4, ipv6, mac, creditcard
  ${BOLD}Primitives${RESET}   number, float, bool, string
  ${BOLD}Time${RESET}         date, timestamp, duration, timezone
  ${BOLD}Color/Geo${RESET}    color, latlng
  ${BOLD}Biz${RESET}          company, jobtitle, currency
  ${BOLD}Web${RESET}          url, slug, hashtag, useragent, method, status
  ${BOLD}Content${RESET}      lorem, animal, food, tech, emoji
  ${BOLD}Meta${RESET}         locales          list all locales
                          (${DIM}${Object.keys(generator.LOCALES).length} locales, ${Object.keys(generator.LOCALES).reduce((s,c)=>s+generator.LOCALES[c].firstNames.length+generator.LOCALES[c].lastNames.length,0).toLocaleString()} names${RESET})

${CYAN}Global options${RESET}
  -n, --count <n>       Generate N items
      --seed <int>      Deterministic output (great for test fixtures)
      --locale <code>   Force a locale (e.g. ru, jp, il, mx, br, ...)
      --cursed          Meme mode (Ligma Balls @ fr-fr-no-cap.io)
      --json            JSON array
      --csv             CSV (when items are objects)
  -h, --help            Show this help
      --version         Print version

${CYAN}Command-specific${RESET}
      --format <fmt>    phone: local|intl|e164 | color: hex|rgb|rgba|hsl|name
      --min <n>         Min value for number
      --max <n>         Max value for number
  -l, --length <n>      String length
      --charset <type>  alpha|numeric|alphanumeric|hex|base62|base64url|lower|upper|special
      --brand <brand>   creditcard: visa|mastercard|amex|discover|jcb|diners
      --type <type>     lorem: words|sentence|sentences|paragraph|paragraphs
      --after <date>    Date after YYYY-MM-DD
      --before <date>   Date before YYYY-MM-DD

${CYAN}Examples${RESET}
  randumb user --locale ru                ${DIM}# Russian name, +7 phone, RUB, Moscow${RESET}
  randumb user --locale il --json          ${DIM}# Israeli user, full JSON${RESET}
  randumb user --locale md                 ${DIM}# Moldovan: Tudor Popa, +373, MDL${RESET}
  randumb email --locale jp -n 5           ${DIM}# 5 Japanese-style emails${RESET}
  randumb phone --locale br                ${DIM}# Brazilian phone +55 11 9...${RESET}
  randumb creditcard --brand visa -n 3     ${DIM}# 3 Luhn-valid test cards${RESET}
  randumb user --seed 42                   ${DIM}# Deterministic fixture${RESET}
  randumb user --cursed --json             ${DIM}# Ligma Balls, Chief Yeet Officer${RESET}
  randumb lorem --type paragraph           ${DIM}# Lorem ipsum paragraph${RESET}
  randumb uuid -n 100                      ${DIM}# 100 UUIDs${RESET}
  randumb latlng --json                    ${DIM}# Random {lat, lng}${RESET}
  randumb locales                          ${DIM}# List every supported locale${RESET}

${CYAN}Locales${RESET}
  ${localeList}

${DIM}// use --seed for reproducible fixtures. use --locale to avoid John Smiths in Russia.${RESET}

  Docs:    https://voiddo.com/tools/randumb/
  Source:  https://github.com/voidd0/randumb
  Catalog: https://voiddo.com/tools/
`);
}

function formatOutput(items, asJson, asCsv) {
  if (asJson) {
    if (items.length === 1 && typeof items[0] === 'object') {
      console.log(JSON.stringify(items[0], null, 2));
    } else if (items.length === 1) {
      console.log(JSON.stringify(items[0]));
    } else {
      console.log(JSON.stringify(items, null, 2));
    }
    return;
  }
  if (asCsv && items.length > 0 && typeof items[0] === 'object') {
    const keys = Object.keys(items[0]);
    console.log(keys.join(','));
    for (const item of items) {
      console.log(keys.map((k) => '"' + String(item[k]).replace(/"/g, '""') + '"').join(','));
    }
    return;
  }
  for (const item of items) {
    if (typeof item === 'object') console.log(JSON.stringify(item, null, 2));
    else console.log('  ' + item);
  }
}

function printLocales() {
  const asJson = hasFlag(['--json']);
  const entries = Object.entries(generator.LOCALES).map(([code, l]) => ({
    code,
    country: l.country,
    currency: l.currency,
    phonePrefix: l.phonePrefix,
    firstNames: l.firstNames.length,
    lastNames: l.lastNames.length,
    cities: l.cities.length,
  }));
  if (asJson) { console.log(JSON.stringify(entries, null, 2)); return; }
  console.log(`\n  ${BOLD}${generator.LOCALES ? Object.keys(generator.LOCALES).length : 0} LOCALES${RESET}`);
  console.log(`  ${DIM}─────────${RESET}\n`);
  console.log(`  ${BOLD}code  country                       currency  phone     names${RESET}`);
  for (const e of entries) {
    const names = e.firstNames + e.lastNames;
    console.log(`  ${CYAN}${e.code.padEnd(4)}${RESET}  ${e.country.padEnd(28)}  ${GREEN}${e.currency.padEnd(7)}${RESET}  ${e.phonePrefix.padEnd(8)}  ${DIM}${names}${RESET}`);
  }
  console.log('');
}

function run() {
  if (!command || hasFlag(['-h', '--help'])) { showHelp(); return; }
  if (hasFlag(['--version'])) { console.log(readPkgVersion()); return; }

  if (command === 'locales') { printLocales(); return; }

  const seedArg = getArg(['--seed']);
  if (seedArg !== null) generator.seed(parseInt(seedArg, 10));

  const count = parseInt(getArg(['-n', '--count'], '1'), 10);
  const cursed = hasFlag(['--cursed']);
  const asJson = hasFlag(['--json']);
  const asCsv = hasFlag(['--csv']);
  const locale = getArg(['--locale']);

  const items = [];

  for (let i = 0; i < count; i++) {
    let result;
    switch (command) {
      case 'name': result = generator.name(cursed, locale); break;
      case 'firstname': case 'first': result = generator.firstName(cursed, locale); break;
      case 'lastname': case 'last': result = generator.lastName(cursed, locale); break;
      case 'email': result = generator.email(cursed, locale); break;
      case 'username': result = generator.username(); break;
      case 'address': result = generator.address(cursed, locale); break;
      case 'phone': {
        const fmt = getArg(['--format'], 'local');
        result = generator.phone(fmt, cursed, locale);
        break;
      }
      case 'country': result = generator.country(locale); break;
      case 'number': {
        const min = parseInt(getArg(['--min'], '0'), 10);
        const max = parseInt(getArg(['--max'], '100'), 10);
        result = generator.number(min, max);
        break;
      }
      case 'float': {
        const min = parseFloat(getArg(['--min'], '0'));
        const max = parseFloat(getArg(['--max'], '1'));
        const dec = parseInt(getArg(['--decimals'], '2'), 10);
        result = generator.float(min, max, dec);
        break;
      }
      case 'bool': result = generator.bool(); break;
      case 'string': {
        const length = parseInt(getArg(['-l', '--length'], '16'), 10);
        const charset = getArg(['--charset'], 'alphanumeric');
        result = generator.string(length, charset);
        break;
      }
      case 'uuid': result = generator.uuid(); break;
      case 'date': {
        const after = getArg(['--after']);
        const before = getArg(['--before']);
        result = generator.date(after, before);
        break;
      }
      case 'timestamp': {
        const after = getArg(['--after']);
        const before = getArg(['--before']);
        result = generator.timestamp(after, before);
        break;
      }
      case 'duration': result = generator.duration(); break;
      case 'timezone': case 'tz': result = generator.timezone(); break;
      case 'ipv4': case 'ip': result = generator.ipv4(); break;
      case 'ipv6': result = generator.ipv6(); break;
      case 'mac': result = generator.mac(); break;
      case 'color': {
        const fmt = getArg(['--format'], 'hex');
        result = generator.color(fmt);
        break;
      }
      case 'latlng': case 'coord': result = generator.latlng(); break;
      case 'company': result = generator.company(); break;
      case 'jobtitle': case 'job': result = generator.jobTitle(); break;
      case 'currency': {
        const min = parseFloat(getArg(['--min'], '0'));
        const max = parseFloat(getArg(['--max'], '1000'));
        const code = getArg(['--code']);
        result = generator.currency(min, max, code, locale);
        break;
      }
      case 'url': result = generator.url(); break;
      case 'slug': {
        const words = parseInt(getArg(['--words'], '3'), 10);
        result = generator.slug(words);
        break;
      }
      case 'hashtag': case 'tag': result = generator.hashtag(); break;
      case 'useragent': case 'ua': result = generator.userAgent(); break;
      case 'method': case 'httpmethod': result = generator.httpMethod(); break;
      case 'status': case 'httpstatus': result = generator.httpStatus(); break;
      case 'lorem': {
        const type = getArg(['--type'], 'sentence');
        const c = parseInt(getArg(['--words-count', '--count'], '1'), 10);
        result = generator.lorem(type, c);
        break;
      }
      case 'animal': result = generator.animal(); break;
      case 'food': result = generator.food(); break;
      case 'tech': case 'techword': result = generator.techWord(); break;
      case 'emoji': result = generator.emoji(); break;
      case 'creditcard': case 'cc': {
        const brand = getArg(['--brand'], 'visa');
        result = generator.creditCard(brand);
        break;
      }
      case 'user': result = generator.user({ cursed, locale }); break;
      default:
        console.error('  Unknown command: ' + command);
        console.error('  Run: randumb --help');
        process.exit(1);
    }
    items.push(result);
  }
  formatOutput(items, asJson, asCsv);
}

run();
