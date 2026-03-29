<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.md">English</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="400" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPL प्रशिक्षण कार्यपुस्तिका - अभ्यास करके सीखें, प्रमाण के माध्यम से सिद्ध करें।

प्रत्येक मॉड्यूल एक XRPL कौशल सिखाता है और एक सत्यापन योग्य प्रमाण उत्पन्न करता है: एक लेनदेन आईडी, एक हस्ताक्षरित रसीद, या एक नैदानिक रिपोर्ट। कोई खाता नहीं, कोई अनावश्यक जानकारी नहीं - केवल दक्षता और रसीदें।

## इंस्टॉल करें

```bash
pipx install xrpl-lab
```

या pip के साथ:

```bash
pip install xrpl-lab
```

Python 3.11+ की आवश्यकता है।

## शुरुआत कैसे करें

```bash
xrpl-lab start
```

गाइडेड लॉन्चर आपको वॉलेट सेटअप, फंडिंग और आपके पहले मॉड्यूल के बारे में बताता है।

### ऑफ़लाइन मोड

```bash
xrpl-lab start --dry-run
```

किसी नेटवर्क की आवश्यकता नहीं है। सीखने के लिए सिमुलेटेड लेनदेन।

## मॉड्यूल

तीन ट्रैक में 12 मॉड्यूल: शुरुआती, मध्यवर्ती और उन्नत।

| # | मॉड्यूल | ट्रैक | आप क्या सीखते हैं | आप क्या सिद्ध करते हैं |
|---|--------|-------|----------------|----------------|
| 1 | रसीद ज्ञान | शुरुआती | भुगतान भेजें, प्रत्येक रसीद फ़ील्ड पढ़ें | लेनदेन आईडी + सत्यापन रिपोर्ट |
| 2 | विफलता ज्ञान | शुरुआती | जानबूझकर लेनदेन को विफल करें, निदान करें, ठीक करें, पुनः सबमिट करें | विफल + ठीक किए गए लेनदेन आईडी का क्रम |
| 3 | ट्रस्ट लाइन्स 101 | शुरुआती | जारीकर्ता बनाएं, ट्रस्ट लाइन सेट करें, टोकन जारी करें | ट्रस्ट लाइन + टोकन बैलेंस |
| 4 | ट्रस्ट लाइन्स का डिबगिंग | शुरुआती | जानबूझकर ट्रस्ट लाइन विफलता, त्रुटि डिकोड, ठीक करें | त्रुटि → ठीक किए गए लेनदेन आईडी का क्रम |
| 5 | DEX ज्ञान | मध्यवर्ती | ऑफर बनाएं, ऑर्डर बुक पढ़ें, रद्द करें | ऑफर बनाएं + रद्द किए गए लेनदेन आईडी |
| 6 | रिजर्व 101 | मध्यवर्ती | खाता स्नैपशॉट, मालिक की संख्या, रिजर्व गणित | स्नैपशॉट का अंतर (पहले/बाद में) |
| 7 | खाता प्रबंधन | मध्यवर्ती | ऑफर रद्द करें, ट्रस्ट लाइन हटाएं, रिजर्व खाली करें | सफाई सत्यापन रिपोर्ट |
| 8 | रसीद ऑडिट | मध्यवर्ती | अपेक्षाओं के साथ लेनदेन को बैच में सत्यापित करें | ऑडिट पैक (MD + CSV + JSON) |
| 9 | AMM तरलता 101 | उन्नत | पूल बनाएं, जमा करें, LP अर्जित करें, वापस लें | AMM जीवनचक्र लेनदेन आईडी |
| 10 | DEX मार्केट मेकिंग 101 | उन्नत | बोली/मांग ऑफर, स्थिति स्नैपशॉट, सफाई | रणनीति लेनदेन आईडी + सफाई रिपोर्ट |
| 11 | इन्वेंट्री गार्डरेल | उन्नत | थ्रेशोल्ड-आधारित उद्धरण, केवल सुरक्षित-साइड प्लेसमेंट | इन्वेंट्री जांच + सुरक्षित लेनदेन आईडी |
| 12 | DEX बनाम AMM जोखिम ज्ञान | उन्नत | DEX और AMM जीवनचक्र की तुलना | तुलना रिपोर्ट + ऑडिट ट्रेल |

## कमांड

```
xrpl-lab start              Guided launcher
xrpl-lab list               Show all modules with status
xrpl-lab run <module_id>    Run a specific module
xrpl-lab status             Progress, wallet, recent txs
xrpl-lab proof-pack         Export shareable proof pack
xrpl-lab certificate        Export completion certificate
xrpl-lab doctor             Run diagnostic checks
xrpl-lab self-check         Alias for doctor
xrpl-lab feedback           Generate issue-ready markdown
xrpl-lab audit              Batch verify transactions
xrpl-lab last-run           Show last module run + audit command
xrpl-lab reset              Wipe local state (requires RESET confirmation)

xrpl-lab wallet create      Create a new wallet
xrpl-lab wallet show        Show wallet info (no secrets)
xrpl-lab fund               Fund wallet from testnet faucet
xrpl-lab send --to <address> --amount <xrp> [--memo <text>]  Send a payment
xrpl-lab verify --tx <id>   Verify a transaction on-ledger
```

सभी कमांड ऑफ़लाइन मोड में लागू होने पर `--dry-run` का समर्थन करते हैं।

## प्रमाण

**प्रमाण पैक** (`xrpl_lab_proof_pack.json`): पूर्ण किए गए मॉड्यूल, लेनदेन आईडी और एक्सप्लोरर लिंक का साझा करने योग्य रिकॉर्ड। इसमें SHA-256 अखंडता हैश शामिल है। कोई गुप्त जानकारी नहीं।

**प्रमाणपत्र** (`xrpl_lab_certificate.json`): पूर्णता का संक्षिप्त रिकॉर्ड।

**रिपोर्ट** (`reports/*.md`): आपने जो किया और सिद्ध किया, उसका मानव-पठनीय सारांश।

**ऑडिट पैक** (`audit_pack_*.json`): SHA-256 अखंडता हैश के साथ बैच सत्यापन परिणाम।

## सुरक्षा और विश्वास मॉडल

**XRPL लैब द्वारा संसाधित डेटा:**
- वॉलेट सीड (स्थानीय रूप से `~/.xrpl-lab/wallet.json` में प्रतिबंधित फ़ाइल अनुमतियों के साथ संग्रहीत)
- मॉड्यूल प्रगति और लेनदेन आईडी (स्थानीय रूप से `~/.xrpl-lab/state.json` में संग्रहीत)
- XRPL टेस्टनेट RPC (सार्वजनिक एंडपॉइंट, लेनदेन स्थानीय रूप से हस्ताक्षरित होने के बाद सबमिट किए जाते हैं)
- टेस्टनेट नल (सार्वजनिक HTTP, केवल आपका पता भेजा जाता है)

**डेटा जो XRPL लैब द्वारा एक्सेस नहीं किया जाता:**
- कोई भी मुख्य नेटवर्क (मेननेट) नहीं, केवल टेस्टनेट।
- किसी भी प्रकार का टेलीमेट्री, एनालिटिक्स या डेटा संग्रह नहीं।
- कोई क्लाउड अकाउंट नहीं, कोई पंजीकरण नहीं, कोई तृतीय-पक्ष एपीआई नहीं।
- प्रमाण पैकों, प्रमाणपत्रों या रिपोर्टों में कभी भी कोई गुप्त जानकारी नहीं होगी।

**अनुमतियाँ:**
- फ़ाइल सिस्टम: केवल `~/.xrpl-lab/` और `./.xrpl-lab/` (स्थानीय कार्यक्षेत्र) फ़ाइलों को पढ़ने/लिखने की अनुमति।
- नेटवर्क: केवल XRPL टेस्टनेट आरपीसी और "फ़ॉसेट" (faucet) तक पहुंच (दोनों को पर्यावरण चर के माध्यम से बदला जा सकता है, और दोनों `--dry-run` विकल्प के साथ वैकल्पिक हैं)।
- किसी भी विशेष अनुमति की आवश्यकता नहीं है।

सुरक्षा नीति के बारे में पूरी जानकारी के लिए [SECURITY.md](SECURITY.md) देखें।

## आवश्यकताएं

- पायथन 3.11 या उच्चतर
- टेस्टनेट के लिए इंटरनेट कनेक्शन (या पूरी तरह से ऑफलाइन मोड के लिए `--dry-run` का उपयोग करें)।

## लाइसेंस

एमआईटी (MIT)

यह [MCP Tool Shop](https://mcp-tool-shop.github.io/) द्वारा बनाया गया है।
