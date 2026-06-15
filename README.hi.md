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

XRPL प्रशिक्षण कार्यपुस्तिका – करके सीखें, प्रमाण के रूप में परिणाम प्रस्तुत करें।

प्रत्येक मॉड्यूल एक XRPL कौशल सिखाता है और एक सत्यापित परिणाम उत्पन्न करता है: एक लेनदेन आईडी,
एक हस्ताक्षरित रसीद, या एक नैदानिक रिपोर्ट। कोई खाता नहीं, कोई अनावश्यक जानकारी नहीं, कोई क्लाउड नहीं – केवल
क्षमता और रसीदें।

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing 11/12 modules completed with quick actions and status panels">
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

निर्देशित लॉन्चर आपको वॉलेट सेटअप, धन और आपके पहले मॉड्यूल में मार्गदर्शन करता है।

### ऑफ़लाइन मोड

```bash
xrpl-lab start --dry-run
```

किसी नेटवर्क की आवश्यकता नहीं है। वर्कफ़्लो सीखने के लिए नकली लेनदेन।

## मॉड्यूल

नौ ट्रैक में 16 मॉड्यूल: बुनियादी बातें, एनएफटी, टोकन, भुगतान, पहचान, डीईएक्स, भंडार, ऑडिट और एएमएम।
पूर्व आवश्यकताएं स्पष्ट रूप से बताई गई हैं – सीएलआई और लिंटर उन्हें लागू करते हैं।

| # | मॉड्यूल | ट्रैक | मोड | आप क्या सीखेंगे | आप क्या साबित करेंगे |
|---|--------|-------|------|----------------|----------------|
| 1 | रसीद साक्षरता | बुनियादी बातें | टेस्टनेट | अंतिम परिणाम एक रसीद है, न कि "भेजा गया" स्थिति – भुगतान भेजें, प्रत्येक रसीद फ़ील्ड पढ़ें। | txid + सत्यापन रिपोर्ट |
| 2 | विफलता साक्षरता | बुनियादी बातें | टेस्टनेट | XRPL त्रुटियों का अर्थ है (tec/tef/tem/ter) – जानबूझकर एक लेनदेन को विफल करें, निदान करें, ठीक करें, पुनः सबमिट करें। | विफल + ठीक किया गया txid अनुक्रम |
| 3 | ट्रस्ट लाइन 101 | बुनियादी बातें | टेस्टनेट | टोकन वैकल्पिक और दिशात्मक होते हैं – जारीकर्ता बनाएं, ट्रस्ट लाइन सेट करें, टोकन जारी करें। | ट्रस्ट लाइन + टोकन बैलेंस |
| 4 | ट्रस्ट लाइनों का डीबगिंग | बुनियादी बातें | टेस्टनेट | ट्रस्ट लाइन त्रुटि कोड को डिकोड करें – जानबूझकर विफलता, त्रुटि डिकोड, ठीक करें। | त्रुटि → फिक्स txid अनुक्रम |
| 5 | डीईएक्स साक्षरता | डेक्स | टेस्टनेट | ऑर्डर बुक निर्माता को खरीदार के साथ जोड़ते हैं – ऑफ़र बनाएं, ऑर्डर बुक पढ़ें, रद्द करें। | ऑफ़र बनाएं + रद्द txid |
| 6 | भंडार 101 | भंडार | टेस्टनेट | प्रत्येक स्वामित्व वाली वस्तु XRP को लॉक करती है – स्नैपशॉट, मालिक की संख्या, भंडार गणित। | पहले/बाद में स्नैपशॉट डेल्टा |
| 7 | खाता स्वच्छता | भंडार | टेस्टनेट | सफाई एक प्राथमिक कौशल है – ऑफ़र रद्द करें, ट्रस्ट लाइन हटाएं, भंडार मुक्त करें। | सफाई सत्यापन रिपोर्ट |
| 8 | रसीद ऑडिट | ऑडिट | टेस्टनेट | ऑडिट इरादे को एन्कोड करते हैं (txid + अपेक्षा + निर्णय) – अपेक्षाओं के साथ बैच में सत्यापित करें। | ऑडिट पैक (MD + CSV + JSON) |
| 9 | एएमएम तरलता 101 | एएमएम | ड्राई-रन | स्थिर उत्पाद (`x*y=k`) मूल्य निष्क्रिय रूप से निर्धारित करते हैं – पूल बनाएं, जमा करें, एलपी अर्जित करें, निकालें। | एएमएम जीवनचक्र txid |
| 10 | डीईएक्स मार्केट मेकिंग 101 | डेक्स | टेस्टनेट | बोली/पूछ मूल्य प्रसार सूची को ट्रैक करते हैं – दोनों पक्षों का उद्धरण दें, स्नैपशॉट स्थिति, साफ करें। | रणनीति txid + स्वच्छता रिपोर्ट |
| 11 | सूची सुरक्षा उपाय | डेक्स | टेस्टनेट | जब सूची कम हो जाती है तो केवल सुरक्षित पक्ष का ही उद्धरण दें – सीमा-आधारित, संरक्षित प्लेसमेंट। | सूची जांच + संरक्षित txid |
| 12 | डीईएक्स बनाम एएमएम जोखिम साक्षरता | एएमएम | ड्राई-रन | अस्थायी नुकसान एएमएम मॉडल की एक विशेषता है – डीईएक्स और एएमएम जीवनचक्र अगल-बगल। | तुलनात्मक रिपोर्ट + ऑडिट ट्रेल |
| 13 | एनएफटी मिंटिंग 101 | एनएफटी | टेस्टनेट | एनएफटी मूल लेज़र वस्तुएं हैं – एक गेम संपत्ति (टैक्सोन, यूआरआई, रॉयल्टी) बनाएं, स्वामित्व को सत्यापित करें। | NFTokenID + ऑन-लेजर सत्यापन |
| 14 | एमपीटी जारी करना 101 | टोकन | टेस्टनेट | एक लेनदेन में एक गेम मुद्रा – एक बहुउद्देशीय टोकन (XLS-33) जारी करें: आपूर्ति सीमा, स्केल, ध्वज। | जारी करने की आईडी + ऑन-लेजर सत्यापन |
| 15 | एस्क्रो 101 | भुगतान | टेस्टनेट | एक निश्चित समय तक XRP को लॉक करें – एक समय-आधारित एस्क्रो बनाएं, इसे ऑन-लेजर पर सत्यापित करें। | एस्क्रो वस्तु + FinishAfter |
| 16 | डीआईडी 101 | पहचान | टेस्टनेट | ऑन-लेजर पहचान – एक विकेंद्रीकृत पहचानकर्ता (XLS-40) को एंकर करें, इसे सत्यापित करें। | डीआईडी वस्तु + यूआरआई |

### ट्रैक

- **बुनियादी बातें** – वॉलेट, भुगतान, ट्रस्ट लाइन, त्रुटि प्रबंधन
- **एनएफटी** – एनएफटी गेम संपत्ति: मिंटिंग, संग्रह, रॉयल्टी (XLS-20)
- **टोकन** – बहुउद्देशीय टोकन (एमपीटी) गेम-मुद्रा जारी करना (XLS-33)
- **भुगतान** – एस्क्रो और समय-लॉक मूल्य
- **पहचान** – विकेंद्रीकृत पहचानकर्ता (डीआईडी, XLS-40)
- **डेक्स** – ऑफ़र, ऑर्डर बुक, मार्केट मेकिंग, सूची प्रबंधन
- **भंडार** – खाता भंडार, मालिक की संख्या, सफाई
- **ऑडिट** – बैच सत्यापन, ऑडिट रिपोर्ट
- **एएमएम** – स्वचालित बाजार निर्माता तरलता, डीईएक्स बनाम एएमएम तुलना

### मोड

- **टेस्टनेट** – XRPL टेस्टनेट पर वास्तविक लेनदेन
- **ड्राई-रन** – नकली लेनदेन के साथ ऑफ़लाइन सैंडबॉक्स (किसी नेटवर्क की आवश्यकता नहीं)

## आदेश

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
xrpl-lab certificate        Export completion certificate
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

सभी आदेशों में, जहां लागू हो, ऑफ़लाइन मोड के लिए `--dry-run` का समर्थन किया जाता है।

## कार्यशाला उपयोग

XRPL लैब को वास्तविक शिक्षण वातावरण के लिए डिज़ाइन किया गया है। कोई खाता नहीं, कोई टेलीमेट्री नहीं, कोई क्लाउड नहीं।
सब कुछ स्थानीय रूप से चलता है।

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

एक सुविधाकर्ता किसी भी शिक्षार्थी के मुद्दे का समर्थन बंडल से निदान कर सकता है, बिना पूरे सत्र को दोहराए। कोई रहस्य शामिल नहीं हैं।

### कार्यशाला प्रवाह

**पूरी तरह से ऑफ़लाइन सैंडबॉक्स** – किसी नेटवर्क की आवश्यकता नहीं:
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**मिश्रित ऑफ़लाइन + टेस्टनेट** – बुनियादी बातों के लिए वास्तविक लेनदेन, उन्नत के लिए सैंडबॉक्स:
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**कैंप → लैब प्रगति** – xrpl-कैंप से जारी रखें:
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## कलाकृतियाँ

**प्रूफ पैक** (`xrpl_lab_proof_pack.json`): पूर्ण किए गए मॉड्यूल, लेनदेन आईडी और एक्सप्लोरर लिंक का साझा करने योग्य रिकॉर्ड। इसमें SHA-256 इंटीग्रिटी हैश शामिल है। कोई गुप्त जानकारी नहीं।

**प्रमाणपत्र** (`xrpl_lab_certificate.json`): संक्षिप्त समापन रिकॉर्ड।

**रिपोर्ट** (`reports/*.md`): आपने जो किया और साबित किया, उसका मानव-पठनीय सारांश।

**ऑडिट पैक** (`audit_pack_*.json`): SHA-256 इंटीग्रिटी हैश के साथ बैच सत्यापन परिणाम।

## सुरक्षा और विश्वास मॉडल

**XRPL लैब द्वारा एक्सेस किया जाने वाला डेटा:**
- वॉलेट सीड (स्थानीय रूप से `~/.xrpl-lab/wallet.json` में सादे पाठ JSON के रूप में संग्रहीत, 0o600 फ़ाइल अनुमतियों और 0o700 पैरेंट निर्देशिका द्वारा सुरक्षित - एन्क्रिप्ट नहीं किया गया)
- मॉड्यूल प्रगति और लेनदेन आईडी ( `~/.xrpl-lab/state.json` में संग्रहीत, tmp + नाम बदलने के माध्यम से परमाणु लेखन)
- XRPL टेस्टनेट RPC (सार्वजनिक एंडपॉइंट, सबमिशन से पहले स्थानीय रूप से हस्ताक्षरित लेनदेन)
- टेस्टनेट फ़ॉसेट (सार्वजनिक HTTP, केवल आपका पता भेजा जाता है)

**XRPL लैब द्वारा एक्सेस नहीं किया जाने वाला डेटा:**
- कोई मेननेट नहीं। केवल टेस्टनेट
- कोई टेलीमेट्री, एनालिटिक्स या किसी भी प्रकार का फोन-होम नहीं
- कोई क्लाउड खाते नहीं, कोई पंजीकरण नहीं, कोई तृतीय-पक्ष API नहीं
- प्रूफ पैक, प्रमाणपत्र, रिपोर्ट या समर्थन बंडलों में कोई गुप्त जानकारी नहीं - कभी नहीं

**अनुमतियाँ और भंडारण स्तर:**
- होम `~/.xrpl-lab/` — निजी गुप्त जानकारी स्तर, 0o700 निर्देशिका + 0o600 वॉलेट फ़ाइल। वॉलेट सीड, डॉक्टर लॉग, ऑडिट पैक संग्रहीत करता है।
- कार्यक्षेत्र `./.xrpl-lab/` — डिज़ाइन किया गया साझा करने योग्य स्तर, 0o755 निर्देशिका। मॉड्यूल रिपोर्ट, प्रूफ पैक, प्रमाणपत्र संग्रहीत करता है। सुविधाकर्ता अनुमति बढ़ाए बिना समीक्षा कर सकते हैं।
- फ़ाइल सिस्टम: केवल उपरोक्त दो स्थानों को पढ़ता/लिखता है
- नेटवर्क: केवल XRPL टेस्टनेट RPC + फ़ॉसेट (दोनों को पर्यावरण चर के माध्यम से बदला जा सकता है, दोनों `--dry-run` के साथ वैकल्पिक)
- किसी भी उन्नत अनुमति की आवश्यकता नहीं है

**डैशबोर्ड सतह (जब `xrpl-lab serve` चल रहा हो):**
- वेबसॉकेट रनर एंडपॉइंट एक ओरिजिन अनुमत सूची लागू करता है (गैर-अनुमत कनेक्शन को कोड 4003 के साथ बंद कर देता है)
- सभी त्रुटि फ़्रेम एक संरचित लिफाफे का उत्सर्जन करते हैं (`code`, `message`, `hint`, `severity`, `icon_hint`) — कोई पथ रिसाव नहीं, कोई आंतरिक-अवस्था रिसाव नहीं
- प्रलेखित बैक-प्रेशर व्यवहार के साथ प्रति-कनेक्शन संदेश कतार सीमित है

पूर्ण सुरक्षा नीति और कार्यशाला सेटअप मार्गदर्शन के लिए [SECURITY.md](SECURITY.md) देखें।

## आवश्यकताएँ

- पायथन 3.11+
- टेस्टनेट के लिए इंटरनेट कनेक्शन (या पूरी तरह से ऑफ़लाइन मोड के लिए `--dry-run` का उपयोग करें)

## लाइसेंस

MIT

[MCP टूल शॉप](https://mcp-tool-shop.github.io/) द्वारा निर्मित
