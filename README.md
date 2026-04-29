# randumb

**Locale-consistent random test data.** 58 locales, 5000+ real names. Country ⟺ phone prefix ⟺ currency ⟺ city are coupled: Russia → Ivan Petrov / +7 / RUB / Moscow. Moldova → Tudor Popa / +373 / MDL / Chișinău. No Russian Johns. No Moldovan shekels. No "San Jose, Arizona". Slavic female surnames are properly inflected. Credit cards are Luhn-valid. Everything is English-Latin, seeded for reproducibility.

Free forever gift from [vøiddo](https://voiddo.com).

```
$ randumb user --locale ru
{
  "id": "a7e1...",
  "locale": "ru",
  "gender": "female",
  "name": "Sofya Novikova",
  "email": "sofya.novikova@mail.ru",
  "phone": "+7 (961) 300-98-38",
  "address": "705 Kirova St, Kazan 852984",
  "country": "Russia",
  "currency": "RUB9024.75",
  "currencyCode": "RUB",
  "jobTitle": "Senior Product Manager",
  "company": "Helix Dynamics"
}
```

## Why randumb

Most faker libraries give you a Jane Smith living at 123 Main Street in Moscow, paying in USD, with an `@bezeqint.net` email. That's not a test fixture — that's a bug report waiting to happen. Your validation code will pass on data that could never occur in production, and fail on real users when you ship.

`randumb` guarantees coherent identities:
- **58 locales** — US, UK, DE, FR, ES, IT, NL, SE, NO, DK, FI, IS, PL, CZ, HU, RO, BG, GR, TR, RU, UA, BY, MD, IL, SA, AE, EG, MA, NG, KE, ZA, JP, KR, CN, HK, SG, MY, ID, PH, TH, VN, IN, PK, BD, BR, AR, MX, CO, CL, PE, CA, AU, NZ, IE, AT, CH, BE, PT.
- **5000+ real names** — US alone has 1700+ first names and 800+ last names from SSA + diaspora pools. Every locale has a properly-sized pool for its population.
- **Country-coupled output** — picking locale `ru` gives you a Russian name, a `+7` phone, RUB currency, and a city that actually exists in Russia.
- **Slavic surname gender inflection** — `Ivanov` (male) → `Ivanova` (female), `Morozov` → `Morozova`, `Moskovskiy` → `Moskovskaya`. Because Valeria Morozov is wrong; Valeria Morozova is right.
- **Luhn-valid test credit cards** — 6 brands (Visa, MC, Amex, Discover, JCB, Diners). Perfect for Stripe test-mode flows.
- **Deterministic seeding** — `--seed 42` gives you the same 100 users every run. Fixtures stay stable; tests don't flake.
- **Latin-ASCII only** — no Cyrillic, no Hebrew, no Arabic, no Kanji. Your logs, BI dashboards, and DB indexes stay clean.

## Install

```bash
npm install -g @v0idd0/randumb
```

Or one-shot with `npx`:

```bash
npx -y @v0idd0/randumb user --locale jp --json
```

## Quickstart

```bash
# Realistic user object, random locale
randumb user

# Forced locale — Russian user with correct phone/currency/address
randumb user --locale ru

# 5 Brazilian users as a JSON array
randumb user --locale br -n 5 --json

# 1000 deterministic fixtures (same output every run)
randumb user --seed 42 -n 1000 --json > fixtures.json

# Individual fields
randumb name --locale de              # German name
randumb email --locale in             # Indian-ish email
randumb phone --locale il             # +972 Israeli mobile
randumb address --locale fr           # Paris / Lyon / ... address
randumb creditcard --brand visa -n 3  # 3 Luhn-valid Visa numbers

# IDs and primitives
randumb uuid -n 100
randumb ipv4
randumb mac
randumb color --format hex            # "#a3b7c9"
randumb latlng --json                 # {"lat": -17.5, "lng": 42.9}

# Content
randumb lorem --type paragraph
randumb company                       # "Nimbus Labs"
randumb jobtitle                      # "Principal Engineer"
randumb slug --words 4                # "refactor-panda-violet-merge-a1f2"
randumb hashtag                       # "#ipsumDolorAmet"
randumb useragent                     # realistic UA string
randumb status                        # common HTTP status code

# Cursed mode (for when you need a dash of chaos)
randumb user --cursed --json          # Ligma Balls, Chief Yeet Officer

# Discover locales
randumb locales                       # 58-row table
randumb locales --json                # JSON catalog
```

## Locale coupling in action

```
$ randumb user --locale md    # Moldova (NOT Russian, NOT shekel)
{
  "name": "Andrei Munteanu",
  "phone": "+373 73 230 278",
  "address": "878 Mihai Eminescu, Orhei MD-4128",
  "currencyCode": "MDL"
}

$ randumb user --locale il    # Israel
{
  "name": "Yoav Gabay",
  "phone": "+972 58-209-5687",
  "address": "205 Ibn Gabirol, Rehovot 1287589",
  "currencyCode": "ILS"
}

$ randumb user --locale jp    # Japan
{
  "name": "Daiki Saito",
  "phone": "+81 88-3559-8793",
  "address": "481 Roppongi, Chiba 601-9872",
  "currencyCode": "JPY"
}

$ randumb user --locale us    # United States (state matches city)
{
  "name": "Michelle Orr",
  "address": "323 Spring St, Jacksonville, FL 76827",
  "currencyCode": "USD"
}
```

## Commands

### Identity
| Command | Output |
|---------|--------|
| `name` | First + last name |
| `firstname` / `first` | First name |
| `lastname` / `last` | Last name (feminized for Slavic-female) |
| `email` | Coherent address derived from name + locale domain |
| `username` | Handle like `wolf_violet42` |
| `user` | Full record with id/name/email/phone/address/country/currency/jobTitle/company |

### Contact
| Command | Output |
|---------|--------|
| `address` | Locale-appropriate postal address |
| `phone` | Phone in locale format (`+972 5X-XXX-XXXX`, `+7 (9XX) XXX-XX-XX`, etc.) |
| `country` | Country name |

### IDs & primitives
| Command | Output |
|---------|--------|
| `uuid` | v4 UUID |
| `ipv4` / `ip` | IPv4 address |
| `ipv6` | IPv6 address |
| `mac` | MAC address |
| `creditcard` / `cc` | Luhn-valid card (`--brand visa\|mastercard\|amex\|discover\|jcb\|diners`) |
| `number` / `float` / `bool` / `string` | Primitives with `--min`/`--max`/`-l`/`--charset` |

### Time & geo
| Command | Output |
|---------|--------|
| `date` / `timestamp` | ISO dates (`--after`/`--before`) |
| `duration` | Short duration like `23m`, `7h`, `12d` |
| `timezone` / `tz` | IANA timezone |
| `color` | `hex` (default) / `rgb` / `rgba` / `hsl` / `name` |
| `latlng` / `coord` | `{lat, lng}` object |

### Business & web
| Command | Output |
|---------|--------|
| `company` / `jobtitle` / `currency` | Corporate data |
| `url` / `slug` / `hashtag` | Web identifiers |
| `useragent` / `ua` | Realistic browser/CLI UA |
| `method` / `status` | HTTP method + common status codes |

### Content
| Command | Output |
|---------|--------|
| `lorem --type words\|sentence\|sentences\|paragraph\|paragraphs` | Lorem ipsum |
| `animal` / `food` / `tech` / `emoji` | Single items |

### Meta
| Command | Output |
|---------|--------|
| `locales` | List all 58 locales with name counts |

## Global options

| Flag | Description |
|------|-------------|
| `-n, --count <n>` | Generate N items |
| `--seed <int>` | Deterministic output (same seed → same data, every run) |
| `--locale <code>` | Force a specific locale (see `randumb locales`) |
| `--cursed` | Meme mode (Ligma Balls, Chief Yeet Officer, `@fr-fr-no-cap.io`) |
| `--json` | JSON array output |
| `--csv` | CSV output (for object-returning commands) |

## Programmatic use

```js
const r = require('@v0idd0/randumb/src/generator');

// Reproducible fixtures
r.seed(42);
const users = Array.from({ length: 1000 }, () => r.user({ locale: 'de' }));

// Mixed locales for realistic prod-shaped data
const countries = ['us', 'gb', 'de', 'fr', 'jp', 'br', 'in'];
const mixed = countries.flatMap((l) => Array.from({ length: 100 }, () => r.user({ locale: l })));

// Validate a credit-card generator
const cc = r.creditCard('amex');       // → "378282..."
r.isValidLuhn(cc);                      // → true

// Weighted picking
const plan = r.weighted([['free', 80], ['starter', 15], ['pro', 5]]);

// Introspect
r.LOCALES.ru.firstNamesMale;            // ['Alexander', 'Dmitry', ...]
r.LOCALES.ru.feminizeSurname('Ivanov'); // 'Ivanova'
```

## Locales

58 countries, ~5200 total names:

| Region | Locales |
|--------|---------|
| **Americas** | `us` `ca` `mx` `br` `ar` `co` `cl` `pe` |
| **Western Europe** | `gb` `ie` `de` `at` `ch` `fr` `be` `nl` `es` `pt` `it` |
| **Nordic** | `se` `no` `dk` `fi` `is` |
| **Central/Eastern Europe** | `pl` `cz` `hu` `ro` `bg` `gr` `tr` |
| **Eastern Slavic** | `ru` `ua` `by` `md` |
| **Middle East & Africa** | `il` `sa` `ae` `eg` `ma` `ng` `ke` `za` |
| **East Asia** | `jp` `kr` `cn` `hk` |
| **SE Asia & Oceania** | `sg` `my` `id` `ph` `th` `vn` `au` `nz` |
| **South Asia** | `in` `pk` `bd` |

## From the same studio

vøiddo builds sharp, free-forever CLIs for devs who are tired of paywalls:

- [`@v0idd0/jsonyo`](https://voiddo.com/tools/jsonyo/) — JSON that yells at you
- [`@v0idd0/tokcount`](https://voiddo.com/tools/tokcount/) — token counter for 60+ LLMs
- [`@v0idd0/ctxstuff`](https://voiddo.com/tools/ctxstuff/) — stuff a repo into an LLM context
- [`@v0idd0/promptdiff`](https://voiddo.com/tools/promptdiff/) — diff two prompts
- [`@v0idd0/httpwut`](https://voiddo.com/tools/httpwut/) — HTTP debugger with phase timing
- [`@v0idd0/gitstats`](https://voiddo.com/tools/gitstats/) — local git analytics
- [`@v0idd0/licenseme`](https://voiddo.com/tools/licenseme/) — LICENSE generator + detector
- [`@v0idd0/envguard`](https://voiddo.com/tools/envguard/) — .env validator + secret scanner
- [`@v0idd0/depcheck`](https://voiddo.com/tools/depcheck/) — offline CVE scanner + unused-deps
- [`@v0idd0/logparse`](https://voiddo.com/tools/logparse/) — structured log parser + aggregator
- [`@v0idd0/cronwtf`](https://voiddo.com/tools/cronwtf/) — explain cron, catch gotchas

Full catalog: [voiddo.com/tools](https://voiddo.com/tools/).

## License

MIT © [vøiddo](https://voiddo.com) — free forever, no asterisks.

## Links

- Docs: https://voiddo.com/tools/randumb/
- Source: https://github.com/voidd0/randumb
- npm: https://npmjs.com/package/@v0idd0/randumb
- Studio: https://voiddo.com
- Issues: https://github.com/voidd0/randumb/issues
- Support: support@voiddo.com

---

Built by [vøiddo](https://voiddo.com/) — a small studio shipping AI-flavoured products, free dev tools, Chrome extensions and weird browser games.
