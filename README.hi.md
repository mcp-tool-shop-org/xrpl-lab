<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.md">English</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="500" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

एक्सआरपीएल प्रशिक्षण कार्यपुस्तिका - करके सीखें, प्रमाण के रूप में परिणाम प्रस्तुत करें।

प्रत्येक मॉड्यूल एक एक्सआरपीएल कौशल सिखाता है और एक सत्यापित परिणाम उत्पन्न करता है: एक लेनदेन आईडी, हस्ताक्षरित रसीद या एक नैदानिक रिपोर्ट। कोई खाता नहीं, कोई अनावश्यक जानकारी नहीं, कोई क्लाउड नहीं - केवल दक्षता और रसीदें।

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing completed modules with quick actions and status panels">
</p>

## स्थापित करें

```bash
pipx install xrpl-lab
```

या पिप के साथ:

```bash
pip install xrpl-lab
```

इसके लिए पायथन 3.11+ की आवश्यकता है।

## त्वरित शुरुआत

```bash
xrpl-lab start
```

निर्देशित लॉन्चर आपको वॉलेट सेटअप, फंडिंग और आपके पहले मॉड्यूल के माध्यम से मार्गदर्शन करता है।

### ऑफ़लाइन मोड

```bash
xrpl-lab start --dry-run
```

किसी नेटवर्क की आवश्यकता नहीं है। वर्कफ़्लो सीखने के लिए नकली लेनदेन।

## मॉड्यूल

<!-- BEGIN curriculum:auto readme-intro -->
<!-- scripts/gen_docs.py द्वारा उत्पन्न - हाथ से संपादित न करें; जनरेटर चलाएं -->
दस ट्रैक में 21 मॉड्यूल: बुनियादी बातें, एनएफटी, टोकन, भुगतान, पहचान, डीईएक्स, भंडार, ऑडिट, एएमएम और कैपस्टोन।
आवश्यक शर्तें स्पष्ट रूप से बताई गई हैं - सीएलआई और लिंटर उन्हें लागू करते हैं।

`#` कॉलम `xrpl-lab list` द्वारा दिखाए गए क्रम से मेल खाता है (मानक ट्रैक क्रम)।
<!-- END curriculum:auto readme-intro -->

<!-- BEGIN curriculum:auto readme-table -->
<!-- scripts/gen_docs.py द्वारा उत्पन्न - हाथ से संपादित न करें; जनरेटर चलाएं -->
| # | मॉड्यूल | ट्रैक | मोड | आवश्यक शर्तें | उत्पन्न करता है |
|---|--------|-------|------|---------------|----------|
| 1 | रसीद साक्षरता | बुनियादी बातें | टेस्टनेट | — | txid, रिपोर्ट |
| 2 | विफलता साक्षरता | बुनियादी बातें | टेस्टनेट | रसीद साक्षरता | txid, रिपोर्ट |
| 3 | ट्रस्ट लाइन्स 101: जारी किए गए मुद्राएँ संबंध के रूप में | बुनियादी बातें | टेस्टनेट | — | txid, रिपोर्ट |
| 4 | ट्रस्ट लाइन्स का डिबगिंग | बुनियादी बातें | टेस्टनेट | ट्रस्ट लाइन्स 101: जारी किए गए मुद्राएँ संबंध के रूप में | txid, रिपोर्ट |
| 5 | एनएफटी मिंटिंग 101: आपकी पहली गेम संपत्ति | एनएफटी | टेस्टनेट | — | txid, रिपोर्ट |
| 6 | एनएफटी मार्केटप्लेस 101: लागू रॉयल्टी के साथ संपत्तियों का व्यापार | एनएफटी | टेस्टनेट | — | txid, रिपोर्ट |
| 7 | गतिशील एनएफटी 101: एक गेम आइटम जो स्तर बढ़ाता है | एनएफटी | टेस्टनेट | — | txid, रिपोर्ट |
| 8 | एमपीटी जारी करना 101: एक लेनदेन में एक गेम मुद्रा | टोकन | टेस्टनेट | — | txid, रिपोर्ट |
| 9 | क्लावबैक 101: जारीकर्ता का पुन: प्राप्ति लीवर | टोकन | टेस्टनेट | — | txid, रिपोर्ट |
| 10 | एस्क्रो 101: समय-लॉक एक्सआरपी | भुगतान | टेस्टनेट | — | txid, रिपोर्ट |
| 11 | एस्क्रो समाप्त 101: लॉक किए गए एक्सआरपी को जारी करना | भुगतान | टेस्टनेट | एस्क्रो 101: समय-लॉक एक्सआरपी | txid, रिपोर्ट |
| 12 | डीआईडी 101: ऑन-लेजर पहचान | पहचान | टेस्टनेट | — | txid, रिपोर्ट |
| 13 | डीईएक्स साक्षरता: ऑफ़र, ऑर्डर पुस्तकें और रद्द करना | डीईएक्स | टेस्टनेट | ट्रस्ट लाइन्स 101: जारी किए गए मुद्राएँ संबंध के रूप में | txid, रिपोर्ट |
| 14 | डीईएक्स मार्केट मेकिंग 101: ऑर्डर बुक पर स्प्रेड कमाना | डीईएक्स | टेस्टनेट | डीईएक्स साक्षरता: ऑफ़र, ऑर्डर पुस्तकें और रद्द करना | txid, रिपोर्ट |
| 15 | डीईएक्स इन्वेंट्री गार्डरेल: एकतरफा न बनें | डीईएक्स | टेस्टनेट | डीईएक्स मार्केट मेकिंग 101: ऑर्डर बुक पर स्प्रेड कमाना | txid, रिपोर्ट |
| 16 | भंडार 101: आपका एक्सआरपी 'कहाँ गया' | भंडार | टेस्टनेट | ट्रस्ट लाइन्स 101: जारी किए गए मुद्राएँ संबंध के रूप में | txid, रिपोर्ट |
| 17 | खाता स्वच्छता: भंडार को मुक्त करना और वस्तुओं को साफ करना | भंडार | टेस्टनेट | भंडार 101: आपका एक्सआरपी 'कहाँ गया' | txid, रिपोर्ट |
| 18 | ऑडिट मोड: बड़े पैमाने पर रसीदों को सत्यापित करें | ऑडिट | टेस्टनेट | रसीद साक्षरता | रिपोर्ट, ऑडिट_पैक |
| 19 | एएमएम तरलता 101: तरलता प्रदान करना और शुल्क अर्जित करना | एएमएम | ड्राई-रन | ट्रस्ट लाइन्स 101: जारी किए गए मुद्राएँ संबंध के रूप में | txid, रिपोर्ट |
| 20 | डीईएक्स बनाम एएमएम जोखिम साक्षरता: ट्रेडिंग रणनीतियों की तुलना करना | एएमएम | ड्राई-रन | डीईएक्स मार्केट मेकिंग 101: ऑर्डर बुक पर स्प्रेड कमाना, एएमएम तरलता 101: तरलता प्रदान करना और शुल्क अर्जित करना | txid, रिपोर्ट |
| 21 | कैपस्टोन: एक्सआरपीएल पर एक न्यूनतम गेम अर्थव्यवस्था बनाएं | कैपस्टोन | टेस्टनेट | एमपीटी जारी करना 101: एक लेनदेन में एक गेम मुद्रा, एनएफटी मिंटिंग 101: आपकी पहली गेम संपत्ति, एस्क्रो 101: समय-लॉक एक्सआरपी, ऑडिट मोड: बड़े पैमाने पर रसीदों को सत्यापित करें | txid, रिपोर्ट, ऑडिट_पैक |
<!-- END curriculum:auto readme-table -->

**उत्पन्न करता है** कॉलम उन कलाकृतियों के प्रकारों की सूची देता है जो प्रत्येक मॉड्यूल उत्पन्न करता है (`txid`, `रिपोर्ट`, `ऑडिट_पैक`); प्रत्येक मॉड्यूल के पेज को [हैंडबुक](https://mcp-tool-shop-org.github.io/xrpl-lab/handbook/modules/) में देखें, जिसमें पूर्ण कौशल विवरण और आप लेजर पर क्या साबित करते हैं।

### ट्रैक

<!-- BEGIN curriculum:auto readme-tracks -->
<!-- scripts/gen_docs.py द्वारा उत्पन्न - हाथ से संपादित न करें; जनरेटर चलाएं -->
- **बुनियादी बातें** - वॉलेट, भुगतान, ट्रस्ट लाइनें, त्रुटि प्रबंधन
- **एनएफटी** - एनएफटी गेम संपत्ति: मिंटिंग, मार्केटप्लेस निपटान, गतिशील एनएफटी (एक्सएलएस-20)
- **टोकन** - बहुउद्देशीय टोकन (एमपीटी) गेम-मुद्रा जारी करना और क्लॉबैक (एक्सएलएस-33)
- **भुगतान** - एस्क्रो और समय-लॉक मूल्य
- **पहचान** - विकेंद्रीकृत पहचानकर्ता (डीआईडी, एक्सएलएस-40)
- **डीईएक्स** - ऑफ़र, ऑर्डर पुस्तकें, मार्केट मेकिंग, इन्वेंट्री प्रबंधन
- **भंडार** - खाता भंडार, मालिक गणना, सफाई
- **ऑडिट** - बैच सत्यापन, ऑडिट रिपोर्ट
- **एएमएम** - स्वचालित बाजार निर्माता तरलता, डीईएक्स बनाम एएमएम तुलना
- **कैपस्टोन** - विभिन्न ट्रैकों में कौशल को मिलाकर एक गेम अर्थव्यवस्था बनाएं
<!-- END curriculum:auto readme-tracks -->

### मोड

- **टेस्टनेट** - एक्सआरपीएल टेस्टनेट पर वास्तविक लेनदेन
- **ड्राई-रन** - नकली लेनदेन के साथ ऑफ़लाइन सैंडबॉक्स (किसी नेटवर्क की आवश्यकता नहीं)

## कमांड

```text
xrpl-lab start              Guided launcher
xrpl-lab list               Show all modules with status and progression
xrpl-lab run <module_id>    Run a specific module
xrpl-lab status [--json]    Progress, curriculum position, blockers, track progress
xrpl-lab cohort-status [--dir DIR] [--format FORMAT]  Aggregate per-learner status across a cohort directory (facilitator)
xrpl-lab session-export [--dir DIR] [--format FORMAT] [--outfile FILE]  Archive all learner artifacts with a SHA-256 manifest
xrpl-lab tracks             Track-level completion summaries
xrpl-lab recovery           Diagnose stuck states, show recovery commands
xrpl-lab lint [glob] [--json] [--no-curriculum]  Validate module files and curriculum
xrpl-lab proof-pack         Export shareable proof pack
xrpl-lab proof generate     Export shareable proof pack (alias of proof-pack)
xrpl-lab proof verify <file>  Verify a proof pack's integrity (SHA-256)
xrpl-lab certificate        Export completion certificate
xrpl-lab cert-verify <file>   Verify a completion certificate's integrity
xrpl-lab doctor             Run diagnostic checks
xrpl-lab self-check         Alias for doctor
xrpl-lab feedback           Generate support bundle (markdown)
xrpl-lab support-bundle [--json] [--verify FILE]  Generate or verify support bundles
xrpl-lab audit              Batch verify transactions
xrpl-lab last-run           Show last module run + audit command
xrpl-lab serve [--port N] [--host H] [--dry-run]  Start web dashboard and API server
xrpl-lab reset [--module MODULE_ID]  Wipe local state OR reset a single module (requires confirmation)
xrpl-lab module init --id ID --track TRACK --title TITLE --time TIME  Scaffold a lint-passing module skeleton

xrpl-lab wallet create      Create a new wallet
xrpl-lab wallet show        Show wallet info (no secrets)
xrpl-lab fund               Fund wallet from testnet faucet
xrpl-lab send --to <address> --amount <xrp> [--memo <text>]  Send a payment
xrpl-lab verify --tx <id>   Verify a transaction on-ledger
```

सभी कमांड उपयुक्त होने पर `--dry-run` का समर्थन करते हैं।

## कार्यशाला उपयोग

एक्सआरपीएल लैब को वास्तविक शिक्षण सेटिंग्स के लिए डिज़ाइन किया गया है। कोई खाता नहीं, कोई टेलीमेट्री नहीं, कोई क्लाउड नहीं। सब कुछ स्थानीय रूप से चलता है।

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### सुविधाकर्ता स्थिति

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### सहायता हस्तांतरण

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

एक सुविधाकर्ता पूरे सत्र को पुन: प्रस्तुत किए बिना किसी भी शिक्षार्थी के मुद्दे का निदान एक समर्थन बंडल से कर सकता है। कोई गुप्त जानकारी शामिल नहीं है।

### कार्यशाला प्रवाह

**पूरी तरह से ऑफ़लाइन सैंडबॉक्स** - किसी नेटवर्क की आवश्यकता नहीं:
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**मिश्रित ऑफ़लाइन + टेस्टनेट** - बुनियादी बातों के लिए वास्तविक लेनदेन, उन्नत के लिए सैंडबॉक्स:
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**कैंप → लैब प्रगति** - xrpl-camp से जारी रखें:
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## कलाकृतियाँ

**प्रूफ पैक** (`xrpl_lab_proof_pack.json`): पूर्ण किए गए मॉड्यूल, लेनदेन आईडी और एक्सप्लोरर लिंक का साझा करने योग्य रिकॉर्ड। इसमें एक SHA-256 अखंडता हैश शामिल है। कोई गुप्त जानकारी नहीं।

**प्रमाणपत्र** (`xrpl_lab_certificate.json`): स्लिम पूर्णता रिकॉर्ड।

**रिपोर्टें** (`reports/*.md`): आपने जो किया और साबित किया, उसका मानव-पठनीय सारांश।

**ऑडिट पैक** (`audit_pack_*.json`): SHA-256 इंटीग्रिटी हैश के साथ बैच सत्यापन परिणाम।

## सुरक्षा और विश्वास मॉडल

**डेटा XRPL लैब जिन पर काम करता है:**
- वॉलेट सीड (स्थानीय रूप से `~/.xrpl-lab/wallet.json` में सादे पाठ JSON के रूप में संग्रहीत, 0o600 फ़ाइल अनुमतियों और 0o700 पैरेंट निर्देशिका द्वारा सुरक्षित - एन्क्रिप्टेड नहीं)
- मॉड्यूल प्रगति और लेनदेन आईडी (स्थानीय रूप से `~/.xrpl-lab/state.json` में संग्रहीत, tmp + नाम बदलने के माध्यम से परमाणु लेखन)
- XRPL टेस्टनेट RPC (सार्वजनिक एंडपॉइंट, सबमिशन से पहले स्थानीय रूप से हस्ताक्षरित लेनदेन)
- टेस्टनेट फ़ॉसेट (सार्वजनिक HTTP, केवल आपका पता भेजा जाता है)

**डेटा XRPL लैब जिन पर काम नहीं करता:**
- कोई मेननेट नहीं। केवल टेस्टनेट
- कोई टेलीमेट्री, एनालिटिक्स या किसी भी प्रकार का फोन-होम नहीं
- कोई क्लाउड खाते नहीं, कोई पंजीकरण नहीं, कोई तृतीय-पक्ष API नहीं
- प्रमाण पैक, प्रमाणपत्र, रिपोर्ट या समर्थन बंडलों में कोई गुप्त जानकारी नहीं - कभी नहीं

**अनुमतियाँ और भंडारण स्तर:**
- होम `~/.xrpl-lab/` — निजी गुप्त जानकारी स्तर, 0o700 निर्देशिका + 0o600 वॉलेट फ़ाइल। वॉलेट सीड, डॉक्टर लॉग, ऑडिट पैक संग्रहीत करता है।
- कार्यक्षेत्र `./.xrpl-lab/` — डिज़ाइन किया गया साझा करने योग्य स्तर, 0o755 निर्देशिका। मॉड्यूल रिपोर्ट, प्रमाण पैक, प्रमाणपत्र संग्रहीत करता है। सुविधाकर्ता अनुमति बढ़ाए बिना समीक्षा कर सकते हैं।
- फ़ाइल सिस्टम: केवल उपरोक्त दो स्थानों पर पढ़ता/लिखता है
- नेटवर्क: केवल XRPL टेस्टनेट RPC + फ़ॉसेट (दोनों को पर्यावरण चर के माध्यम से बदला जा सकता है, दोनों `--dry-run` के साथ वैकल्पिक)
- किसी भी उन्नत अनुमति की आवश्यकता नहीं है

**डैशबोर्ड सतह (जब `xrpl-lab serve` चल रहा हो):**
- वेबसॉकेट रनर एंडपॉइंट एक उत्पत्ति अनुमति सूची लागू करता है (गैर-अनुमत कनेक्शन को कोड 4003 के साथ बंद कर देता है)
- सभी त्रुटि फ़्रेम एक संरचित लिफाफे का उत्सर्जन करते हैं (`code`, `message`, `hint`, `severity`, `icon_hint`) — कोई पथ रिसाव नहीं, कोई आंतरिक-अवस्था रिसाव नहीं
- प्रलेखित बैक-प्रेशर व्यवहार के साथ प्रति-कनेक्शन संदेश कतार सीमित है

पूर्ण सुरक्षा नीति और कार्यशाला सेटअप मार्गदर्शन के लिए [SECURITY.md](SECURITY.md) देखें।

## आवश्यकताएं

- पायथन 3.11+
- टेस्टनेट के लिए इंटरनेट कनेक्शन (या पूरी तरह से ऑफ़लाइन मोड के लिए `--dry-run` का उपयोग करें)

## लाइसेंस

MIT

[MCP टूल शॉप](https://mcp-tool-shop.github.io/) द्वारा निर्मित
