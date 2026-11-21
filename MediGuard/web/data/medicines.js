/*
 * MediGuard - the knowledge base the agent reasons with.
 *
 * MEDICINES     common Indian brands + their generic equivalents
 * SALTS         how each salt can be spelt on a pack (a regular expression)
 * BATCH_ALERTS  batches reported as spurious / not of standard quality
 * CHECKLIST     things a person can see with their own eyes
 *
 * To add a medicine, copy one block and change it.
 *   brand      name shown to the user
 *   match      how the brand is printed: name word, strength number, extra word
 *              e.g. "MONTAIR LC" -> { name: "MONTAIR", extra: "LC" }
 *   company    the company that markets it
 *   companyKeys words that identify that company on a pack (UPPER CASE)
 *   salts      [salt, strength, unit] - two brands with the same salts and
 *              strengths are alternatives for each other
 *   generic    true for the low-cost generic (Jan Aushadhi) version
 *
 * Brand data was put together for a college project. Always confirm with a
 * pharmacist or doctor before switching medicines.
 */
(function (root) {
  "use strict";

  const GENERIC_SOURCE = "Generic - ask at a Jan Aushadhi Kendra or licensed pharmacy";

  const MEDICINES = [
    // ---------- Paracetamol 650 mg ----------
    { brand: "Dolo 650", match: { name: "DOLO", number: "650" }, company: "Micro Labs Ltd", companyKeys: ["MICRO LABS"],
      form: "Tablet", rx: false, use: "Fever, body pain", salts: [["Paracetamol", 650, "mg"]] },
    { brand: "Calpol 650", match: { name: "CALPOL", number: "650" }, company: "GSK", companyKeys: ["GLAXOSMITHKLINE", "GSK", "HALEON"],
      form: "Tablet", rx: false, use: "Fever, body pain", salts: [["Paracetamol", 650, "mg"]] },
    { brand: "Pacimol 650", match: { name: "PACIMOL", number: "650" }, company: "Ipca Laboratories", companyKeys: ["IPCA"],
      form: "Tablet", rx: false, use: "Fever, body pain", salts: [["Paracetamol", 650, "mg"]] },
    { brand: "Paracetamol 650 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: false, use: "Fever, body pain", salts: [["Paracetamol", 650, "mg"]] },

    // ---------- Paracetamol 500 mg ----------
    { brand: "Crocin Advance", match: { name: "CROCIN", extra: "ADVANCE" }, company: "Haleon (GSK)", companyKeys: ["HALEON", "GLAXOSMITHKLINE", "GSK"],
      form: "Tablet", rx: false, use: "Fever, headache", salts: [["Paracetamol", 500, "mg"]] },
    { brand: "Calpol 500", match: { name: "CALPOL", number: "500" }, company: "GSK", companyKeys: ["GLAXOSMITHKLINE", "GSK", "HALEON"],
      form: "Tablet", rx: false, use: "Fever, headache", salts: [["Paracetamol", 500, "mg"]] },
    { brand: "Paracetamol 500 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: false, use: "Fever, headache", salts: [["Paracetamol", 500, "mg"]] },

    // ---------- Pantoprazole 40 mg ----------
    { brand: "Pan 40", match: { name: "PAN", number: "40" }, company: "Alkem Laboratories", companyKeys: ["ALKEM"],
      form: "Tablet", rx: true, use: "Acidity, ulcers", salts: [["Pantoprazole", 40, "mg"]] },
    { brand: "Pantocid 40", match: { name: "PANTOCID", number: "40" }, company: "Sun Pharma", companyKeys: ["SUN PHARMA"],
      form: "Tablet", rx: true, use: "Acidity, ulcers", salts: [["Pantoprazole", 40, "mg"]] },
    { brand: "Pantodac 40", match: { name: "PANTODAC", number: "40" }, company: "Zydus", companyKeys: ["ZYDUS", "CADILA"],
      form: "Tablet", rx: true, use: "Acidity, ulcers", salts: [["Pantoprazole", 40, "mg"]] },
    { brand: "Pantoprazole 40 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Acidity, ulcers", salts: [["Pantoprazole", 40, "mg"]] },

    // ---------- Amoxycillin 500 mg + Clavulanic acid 125 mg ----------
    { brand: "Augmentin 625 Duo", match: { name: "AUGMENTIN", number: "625" }, company: "GSK", companyKeys: ["GLAXOSMITHKLINE", "GSK"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Amoxycillin", 500, "mg"], ["Clavulanic acid", 125, "mg"]] },
    { brand: "Clavam 625", match: { name: "CLAVAM", number: "625" }, company: "Alkem Laboratories", companyKeys: ["ALKEM"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Amoxycillin", 500, "mg"], ["Clavulanic acid", 125, "mg"]] },
    { brand: "Moxikind-CV 625", match: { name: "MOXIKIND", number: "625", extra: "CV" }, company: "Mankind Pharma", companyKeys: ["MANKIND"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Amoxycillin", 500, "mg"], ["Clavulanic acid", 125, "mg"]] },
    { brand: "Amoxycillin 500 mg + Clavulanic acid 125 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Amoxycillin", 500, "mg"], ["Clavulanic acid", 125, "mg"]] },

    // ---------- Azithromycin 500 mg ----------
    { brand: "Azithral 500", match: { name: "AZITHRAL", number: "500" }, company: "Alembic Pharmaceuticals", companyKeys: ["ALEMBIC"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Azithromycin", 500, "mg"]] },
    { brand: "Azee 500", match: { name: "AZEE", number: "500" }, company: "Cipla", companyKeys: ["CIPLA"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Azithromycin", 500, "mg"]] },
    { brand: "Zithrox 500", match: { name: "ZITHROX", number: "500" }, company: "Macleods Pharmaceuticals", companyKeys: ["MACLEODS"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Azithromycin", 500, "mg"]] },
    { brand: "Azithromycin 500 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Azithromycin", 500, "mg"]] },

    // ---------- Metformin 500 mg ----------
    { brand: "Glycomet 500", match: { name: "GLYCOMET", number: "500" }, company: "USV", companyKeys: ["USV"],
      form: "Tablet", rx: true, use: "Type 2 diabetes", salts: [["Metformin", 500, "mg"]] },
    { brand: "Glyciphage 500", match: { name: "GLYCIPHAGE", number: "500" }, company: "Franco-Indian Pharmaceuticals", companyKeys: ["FRANCO"],
      form: "Tablet", rx: true, use: "Type 2 diabetes", salts: [["Metformin", 500, "mg"]] },
    { brand: "Metformin 500 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Type 2 diabetes", salts: [["Metformin", 500, "mg"]] },

    // ---------- Telmisartan 40 mg ----------
    { brand: "Telma 40", match: { name: "TELMA", number: "40" }, company: "Glenmark Pharmaceuticals", companyKeys: ["GLENMARK"],
      form: "Tablet", rx: true, use: "High blood pressure", salts: [["Telmisartan", 40, "mg"]] },
    { brand: "Telmikind 40", match: { name: "TELMIKIND", number: "40" }, company: "Mankind Pharma", companyKeys: ["MANKIND"],
      form: "Tablet", rx: true, use: "High blood pressure", salts: [["Telmisartan", 40, "mg"]] },
    { brand: "Telsartan 40", match: { name: "TELSARTAN", number: "40" }, company: "Dr. Reddy's Laboratories", companyKeys: ["REDDY"],
      form: "Tablet", rx: true, use: "High blood pressure", salts: [["Telmisartan", 40, "mg"]] },
    { brand: "Telmisartan 40 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "High blood pressure", salts: [["Telmisartan", 40, "mg"]] },

    // ---------- Amlodipine 5 mg ----------
    { brand: "Amlong 5", match: { name: "AMLONG", number: "5" }, company: "Micro Labs Ltd", companyKeys: ["MICRO LABS"],
      form: "Tablet", rx: true, use: "High blood pressure", salts: [["Amlodipine", 5, "mg"]] },
    { brand: "Stamlo 5", match: { name: "STAMLO", number: "5" }, company: "Dr. Reddy's Laboratories", companyKeys: ["REDDY"],
      form: "Tablet", rx: true, use: "High blood pressure", salts: [["Amlodipine", 5, "mg"]] },
    { brand: "Amlokind 5", match: { name: "AMLOKIND", number: "5" }, company: "Mankind Pharma", companyKeys: ["MANKIND"],
      form: "Tablet", rx: true, use: "High blood pressure", salts: [["Amlodipine", 5, "mg"]] },
    { brand: "Amlodipine 5 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "High blood pressure", salts: [["Amlodipine", 5, "mg"]] },

    // ---------- Cetirizine 10 mg ----------
    { brand: "Okacet", match: { name: "OKACET" }, company: "Cipla", companyKeys: ["CIPLA"],
      form: "Tablet", rx: false, use: "Allergy, cold", salts: [["Cetirizine", 10, "mg"]] },
    { brand: "Cetirizine 10 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: false, use: "Allergy, cold", salts: [["Cetirizine", 10, "mg"]] },

    // ---------- Montelukast 10 mg + Levocetirizine 5 mg ----------
    { brand: "Montair LC", match: { name: "MONTAIR", extra: "LC" }, company: "Cipla", companyKeys: ["CIPLA"],
      form: "Tablet", rx: true, use: "Allergy, asthma", salts: [["Montelukast", 10, "mg"], ["Levocetirizine", 5, "mg"]] },
    { brand: "Montek LC", match: { name: "MONTEK", extra: "LC" }, company: "Sun Pharma", companyKeys: ["SUN PHARMA"],
      form: "Tablet", rx: true, use: "Allergy, asthma", salts: [["Montelukast", 10, "mg"], ["Levocetirizine", 5, "mg"]] },
    { brand: "Montelukast 10 mg + Levocetirizine 5 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Allergy, asthma", salts: [["Montelukast", 10, "mg"], ["Levocetirizine", 5, "mg"]] },

    // ---------- Atorvastatin 10 mg ----------
    { brand: "Atorva 10", match: { name: "ATORVA", number: "10" }, company: "Zydus", companyKeys: ["ZYDUS", "CADILA"],
      form: "Tablet", rx: true, use: "High cholesterol", salts: [["Atorvastatin", 10, "mg"]] },
    { brand: "Lipitor 10", match: { name: "LIPITOR", number: "10" }, company: "Pfizer", companyKeys: ["PFIZER", "VIATRIS"],
      form: "Tablet", rx: true, use: "High cholesterol", salts: [["Atorvastatin", 10, "mg"]] },
    { brand: "Storvas 10", match: { name: "STORVAS", number: "10" }, company: "Sun Pharma", companyKeys: ["SUN PHARMA", "RANBAXY"],
      form: "Tablet", rx: true, use: "High cholesterol", salts: [["Atorvastatin", 10, "mg"]] },
    { brand: "Atorvastatin 10 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "High cholesterol", salts: [["Atorvastatin", 10, "mg"]] },

    // ---------- Aspirin 75 mg ----------
    { brand: "Ecosprin 75", match: { name: "ECOSPRIN", number: "75" }, company: "USV", companyKeys: ["USV"],
      form: "Tablet", rx: true, use: "Blood thinner (heart)", salts: [["Aspirin", 75, "mg"]] },
    { brand: "Aspirin 75 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Blood thinner (heart)", salts: [["Aspirin", 75, "mg"]] },

    // ---------- Ibuprofen 400 mg + Paracetamol 325 mg ----------
    { brand: "Combiflam", match: { name: "COMBIFLAM" }, company: "Sanofi", companyKeys: ["SANOFI"],
      form: "Tablet", rx: false, use: "Pain, fever", salts: [["Ibuprofen", 400, "mg"], ["Paracetamol", 325, "mg"]] },
    { brand: "Ibugesic Plus", match: { name: "IBUGESIC", extra: "PLUS" }, company: "Cipla", companyKeys: ["CIPLA"],
      form: "Tablet", rx: false, use: "Pain, fever", salts: [["Ibuprofen", 400, "mg"], ["Paracetamol", 325, "mg"]] },
    { brand: "Ibuprofen 400 mg + Paracetamol 325 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: false, use: "Pain, fever", salts: [["Ibuprofen", 400, "mg"], ["Paracetamol", 325, "mg"]] },

    // ---------- Levothyroxine 50 mcg ----------
    { brand: "Thyronorm 50", match: { name: "THYRONORM", number: "50" }, company: "Abbott", companyKeys: ["ABBOTT"],
      form: "Tablet", rx: true, use: "Thyroid (hypothyroidism)", salts: [["Levothyroxine", 50, "mcg"]] },
    { brand: "Thyrox 50", match: { name: "THYROX", number: "50" }, company: "Macleods Pharmaceuticals", companyKeys: ["MACLEODS"],
      form: "Tablet", rx: true, use: "Thyroid (hypothyroidism)", salts: [["Levothyroxine", 50, "mcg"]] },
    { brand: "Levothyroxine 50 mcg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Thyroid (hypothyroidism)", salts: [["Levothyroxine", 50, "mcg"]] },

    // ---------- Cefixime 200 mg ----------
    { brand: "Taxim-O 200", match: { name: "TAXIM", number: "200", extra: "O" }, company: "Alkem Laboratories", companyKeys: ["ALKEM"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Cefixime", 200, "mg"]] },
    { brand: "Zifi 200", match: { name: "ZIFI", number: "200" }, company: "FDC Ltd", companyKeys: ["FDC"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Cefixime", 200, "mg"]] },
    { brand: "Cefixime 200 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Cefixime", 200, "mg"]] },

    // ---------- Ciprofloxacin 500 mg ----------
    { brand: "Ciplox 500", match: { name: "CIPLOX", number: "500" }, company: "Cipla", companyKeys: ["CIPLA"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Ciprofloxacin", 500, "mg"]] },
    { brand: "Cifran 500", match: { name: "CIFRAN", number: "500" }, company: "Sun Pharma", companyKeys: ["SUN PHARMA", "RANBAXY"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Ciprofloxacin", 500, "mg"]] },
    { brand: "Ciprofloxacin 500 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Ciprofloxacin", 500, "mg"]] },

    // ---------- Omeprazole 20 mg ----------
    { brand: "Omez 20", match: { name: "OMEZ", number: "20" }, company: "Dr. Reddy's Laboratories", companyKeys: ["REDDY"],
      form: "Capsule", rx: true, use: "Acidity, ulcers", salts: [["Omeprazole", 20, "mg"]] },
    { brand: "Omeprazole 20 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Capsule", rx: true, use: "Acidity, ulcers", salts: [["Omeprazole", 20, "mg"]] },

    // ---------- Mefenamic acid 250 mg + Dicyclomine 10 mg ----------
    { brand: "Meftal-Spas", match: { name: "MEFTAL", extra: "SPAS" }, company: "Blue Cross Laboratories", companyKeys: ["BLUE CROSS"],
      form: "Tablet", rx: true, use: "Stomach cramps, period pain", salts: [["Mefenamic acid", 250, "mg"], ["Dicyclomine", 10, "mg"]] },
    { brand: "Mefenamic acid 250 mg + Dicyclomine 10 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Stomach cramps, period pain", salts: [["Mefenamic acid", 250, "mg"], ["Dicyclomine", 10, "mg"]] },

    // ---------- Fexofenadine 120 mg ----------
    { brand: "Allegra 120", match: { name: "ALLEGRA", number: "120" }, company: "Sanofi", companyKeys: ["SANOFI"],
      form: "Tablet", rx: true, use: "Allergy", salts: [["Fexofenadine", 120, "mg"]] },
    { brand: "Fexofenadine 120 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Allergy", salts: [["Fexofenadine", 120, "mg"]] },

    // ---------- Calcium carbonate 1250 mg + Vitamin D3 250 IU ----------
    { brand: "Shelcal 500", match: { name: "SHELCAL", number: "500" }, company: "Torrent Pharmaceuticals", companyKeys: ["TORRENT"],
      form: "Tablet", rx: false, use: "Calcium / vitamin D supplement", salts: [["Calcium carbonate", 1250, "mg"], ["Vitamin D3", 250, "IU"]] },
    { brand: "Calcium and Vitamin D3 Tablets (Calcium carbonate 1250 mg + Vitamin D3 250 IU)", generic: true, nameRe: "CALC[IL]UM\\s+AND\\s+VITAMIN\\s*D", company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: false, use: "Calcium / vitamin D supplement", salts: [["Calcium carbonate", 1250, "mg"], ["Vitamin D3", 250, "IU"]] },

    // ---------- Aceclofenac 100 mg + Paracetamol 325 mg + Chlorzoxazone 250 mg (muscle relaxant combo) ----------
    { brand: "Megaceclo MR", match: { name: "MEGACECLO", extra: "MR" }, company: "Aristo Pharmaceuticals", companyKeys: ["ARISTO", "MARINE MEDICARE"],
      form: "Tablet", rx: true, use: "Muscle pain, back pain", salts: [["Aceclofenac", 100, "mg"], ["Paracetamol", 325, "mg"], ["Chlorzoxazone", 250, "mg"]] },
    { brand: "Zerodol-MR", match: { name: "ZERODOL", extra: "MR" }, company: "Ipca Laboratories", companyKeys: ["IPCA"],
      form: "Tablet", rx: true, use: "Muscle pain, back pain", salts: [["Aceclofenac", 100, "mg"], ["Paracetamol", 325, "mg"], ["Chlorzoxazone", 250, "mg"]] },
    { brand: "Aceclofenac 100 mg + Paracetamol 325 mg + Chlorzoxazone 250 mg", generic: true, company: GENERIC_SOURCE, companyKeys: [],
      form: "Tablet", rx: true, use: "Muscle pain, back pain", salts: [["Aceclofenac", 100, "mg"], ["Paracetamol", 325, "mg"], ["Chlorzoxazone", 250, "mg"]] },

    // ---------- more brands from real strips ----------
    { brand: "Fixim DT 200", match: { name: "FIXIM", number: "200" }, company: "Ajanta Pharma", companyKeys: ["AJANTA", "SCOTT-EDIL", "SCOTT EDIL"],
      form: "Dispersible tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Cefixime", 200, "mg"]] },
    { brand: "Duasafe 625", match: { name: "DUASAFE", number: "625" }, company: "Ajanta Pharma", companyKeys: ["AJANTA", "ALPS"],
      form: "Tablet", rx: true, use: "Bacterial infections (antibiotic)", salts: [["Amoxycillin", 500, "mg"], ["Clavulanic acid", 125, "mg"]] },

    // ---------- Vitamin B-Complex Tablets NFI (Prophylactic) - government formulary ----------
    { brand: "Vitamin B-Complex Tablets NFI (Prophylactic)", generic: true, nameRe: "B[\\s.\\-]*COMPLEX", company: GENERIC_SOURCE, companyKeys: ["EUROKEM"],
      form: "Tablet", rx: false, use: "Vitamin B supplement",
      salts: [["Vitamin B1", 2, "mg"], ["Vitamin B2", 2, "mg"], ["Vitamin B6", 0.5, "mg"], ["Niacinamide", 25, "mg"], ["Calcium pantothenate", 1, "mg"]] },
  ];

  // How each salt may be written on a pack (checked against the UPPER CASE text)
  const SALTS = {
    "Paracetamol": "PARACETAMOL|ACETAMINOPHEN",
    "Pantoprazole": "PANTOPRAZOLE",
    "Amoxycillin": "AMOX[YI]CILLIN",
    "Clavulanic acid": "CLAVULAN",
    "Azithromycin": "AZITHROMYCIN",
    "Metformin": "METFORMIN",
    "Telmisartan": "TELMISARTAN",
    "Amlodipine": "AMLODIPINE",
    "Cetirizine": "CETIRIZINE",
    "Montelukast": "MONTELUKAST",
    "Levocetirizine": "LEVOCETIRIZINE",
    "Atorvastatin": "ATORVASTATIN",
    "Aspirin": "ASPIRIN|ACETYLSALICYLIC",
    "Ibuprofen": "IBUPROFEN",
    "Levothyroxine": "THYROXINE",
    "Cefixime": "CEFIXIME",
    "Ciprofloxacin": "CIPROFLOXACIN",
    "Omeprazole": "OMEPRAZOLE",
    "Mefenamic acid": "MEFENAMIC",
    "Dicyclomine": "DICYCLOMINE|DICYCLOVERINE",
    "Fexofenadine": "FEXOFENADINE",
    "Calcium carbonate": "CALC[IL]UM|CALCIU",
    "Aceclofenac": "ACECLOFENAC|ACECLOFEN",
    "Chlorzoxazone": "CHLORZOXAZONE|CHLORZOX",
    "Vitamin B1": "VITAMIN\\s*B\\s*1|THIAMINE",
    "Vitamin B2": "VITAMIN\\s*B\\s*2|RIBOFLAVIN",
    "Vitamin B6": "VITAMIN\\s*B\\s*6|PYRIDOXINE",
    "Niacinamide": "NIACINAMIDE|NICOTINAMIDE",
    "Calcium pantothenate": "PANTOTHENATE",
    "Vitamin D3": "VITAMIN\\s*D[3SYZ:]?\\b|CHOLECALCIFEROL",
  };

  // Reported batches. THESE ARE SAMPLE ENTRIES for the demo.
  // Replace them with the monthly "Drug Alert" list published by CDSCO
  // (cdsco.gov.in -> Drug Alerts) or your State Drug Controller.
  const BATCH_ALERTS = [
    { batch: "FAKE2291", brand: "Crocin Advance", status: "Spurious (sample entry)", source: "Demo data - replace with the CDSCO drug alert list" },
    { batch: "NSQ0099", brand: "Pan 40", status: "Not of standard quality (sample entry)", source: "Demo data - replace with the CDSCO drug alert list" },
  ];

  // What the person can check with their eyes. weight = how much it adds to the risk score.
  const CHECKLIST = [
    { id: "sealBroken",   weight: 25, label: "Seal, foil or strip is broken, re-glued or tampered" },
    { id: "spelling",     weight: 25, label: "Spelling or grammar mistakes on the pack" },
    { id: "poorPrint",    weight: 20, label: "Print or logo is blurry, smudged, faded or uneven" },
    { id: "differentLook",weight: 25, label: "Colour, size, shape, taste or smell differs from usual" },
    { id: "tooCheap",     weight: 15, label: "Price is far lower than usual / unusual big discount" },
    { id: "noBill",       weight: 15, label: "Bought without a bill, or from an unlicensed / unknown seller" },
    { id: "noEffect",     weight: 15, label: "It didn't work as before, or caused an unusual reaction" },
    { id: "govtSupply",   weight: 25, label: "Strip says \"Government supply - Not for sale\" but you bought it in a shop" },
  ];

  const data = { MEDICINES, SALTS, BATCH_ALERTS, CHECKLIST };
  if (typeof module !== "undefined" && module.exports) module.exports = data;
  else root.MEDI_DATA = data;
})(typeof self !== "undefined" ? self : this);
