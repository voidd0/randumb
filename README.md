# randumb

Generates random test data that stays consistent within one country: name, email domain, phone prefix, currency and city fit together. It can be seeded for repeatable fixtures.

[![npm](https://img.shields.io/npm/v/@v0idd0/randumb?color=00f6d0&labelColor=050914)](https://www.npmjs.com/package/@v0idd0/randumb)
[![test](https://github.com/voidd0/randumb/actions/workflows/test.yml/badge.svg)](https://github.com/voidd0/randumb/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-MIT-00f6d0?labelColor=050914)](LICENSE)

## Install

```bash
npm install -g @v0idd0/randumb
```

Or run it once without installing: `npx @v0idd0/randumb --help`. Needs Node.js 18 or newer. No dependencies.

## Example

A user whose name, email domain, phone prefix, currency and city all fit one country. Output from a real run on 2026-11-26 (`createdAt` is relative to the current date):

```console
$ randumb user --locale ru --seed 5 --json
{
  "id": "b7e3cba0-74e4-4cb4-8c34-17f31d56f463",
  "locale": "ru",
  "name": "Arina Vasileva",
  "email": "avasileva59@rambler.ru",
  "phone": "+7 (972) 890-56-82",
  "address": "649 Sovetskaya St, Rostov-on-Don 619857",
  "country": "Russia",
  "currency": "₽3158.68",
  "currencyCode": "RUB",
  "jobTitle": "Business Analyst",
  "company": "Mosaic Labs",
  "createdAt": "2026-11-01T16:49:21.664Z",
  "gender": "female"
}
```

The same `--seed` gives the same values every time. Two German phone numbers:

```console
$ randumb phone --locale de -n 2 --seed 7
  +49 41 1557624
  +49 977 7291258
```


## Usage

```text
randumb v2.0.6
locale-consistent random test data

Usage
  randumb <command> [options]

Commands
  Identity     name, firstname, lastname, email, username, user
  Contact      address, phone, country
  IDs          uuid, ipv4, ipv6, mac, creditcard
  Primitives   number, float, bool, string
  Time         date, timestamp, duration, timezone
  Color/Geo    color, latlng
  Biz          company, jobtitle, currency
  Web          url, slug, hashtag, useragent, method, status
  Content      lorem, animal, food, tech, emoji
  Meta         locales          list all locales
                          (58 locales, 5,182 first and last names)

Global options
  -n, --count <n>       Generate N items
      --seed <int>      Deterministic output (great for test fixtures)
      --locale <code>   Force a locale (e.g. ru, jp, il, mx, br, ...)
      --cursed          Joke data (silly placeholder names and places)
      --json            JSON array
      --csv             CSV (when items are objects)
  -h, --help            Show this help
      --version         Print version

Command-specific
      --format <fmt>    phone: local|intl|e164 | color: hex|rgb|rgba|hsl|name
      --min <n>         Min value for number
      --max <n>         Max value for number
  -l, --length <n>      String length
      --charset <type>  alpha|numeric|alphanumeric|hex|base62|base64url|lower|upper|special
      --brand <brand>   creditcard: visa|mastercard|amex|discover|jcb|diners
      --type <type>     lorem: words|sentence|sentences|paragraph|paragraphs
      --after <date>    Date after YYYY-MM-DD
      --before <date>   Date before YYYY-MM-DD

Examples
  randumb user --locale ru                # Russian name, +7 phone, RUB, Moscow
  randumb user --locale il --json          # Israeli user, full JSON
  randumb user --locale md                 # Moldovan name, +373 phone, MDL
  randumb email --locale jp -n 5           # 5 Japanese-style emails
  randumb phone --locale br                # Brazilian phone +55 11 9...
  randumb creditcard --brand visa -n 3     # 3 Luhn-valid test cards
  randumb user --seed 42                   # Deterministic fixture
  randumb user --cursed --json             # joke data as JSON
  randumb lorem --type paragraph           # Lorem ipsum paragraph
  randumb uuid -n 100                      # 100 UUIDs
  randumb latlng --json                    # Random {lat, lng}
  randumb locales                          # List every supported locale

Locales
  us, ca, gb, ie, au, nz, de, at, ch, fr, be, nl, es, pt, it, se, no, dk, fi, is, pl, cz, hu, ro, bg, gr, tr, ru, ua, by, md, il, sa, ae, eg, ng, za, ke, ma, jp, kr, cn, hk, sg, my, id, ph, th, vn, in, pk, bd, br, ar, mx, co, cl, pe

Use --seed for reproducible fixtures and --locale to match names to a country.

Docs and issues: https://github.com/voidd0/randumb
```

## Counts

Counted from the data in the code: 58 locales and 5,182 first and last name entries (counted per locale, so a name used in two locales counts twice). Run `randumb locales` to list them.

## License

MIT, see [LICENSE](LICENSE).

---

Made by [vøiddo](https://voiddo.com/?src=gh). More command line tools: [voiddo.com/packages](https://voiddo.com/packages/?src=gh).
We also run data scrapers for job boards, shops and ad libraries: [voiddo.com/scrapers](https://voiddo.com/scrapers/?src=gh).
