# ILC Case Management Tools

Ferramentas Python para geração de documentos de imigração (LORs, Personal Statements, Packages).

## Instalação

```bash
cd tools
pip install -r requirements.txt
```

## Ferramentas Disponíveis

### 1. LOR Generator

Gera Letters of Recommendation com 5 personas distintas.

**Personas:**
- `executive` - Arial 11pt, direto, resultados
- `technical` - Calibri 11pt, factual, métricas
- `academic` - Garamond 12pt, com tabs, acadêmico
- `mentor` - Georgia 11pt, com tabs, pessoal
- `corporate` - Times New Roman 12pt, formal

**Exemplo:**
```python
from lor_generator import LORGenerator

generator = LORGenerator(
    persona="executive",
    beneficiary_name="John Doe",
    visa_type="EB-2 NIW",
    field="cybersecurity",
)

paragraphs = [
    generator.get_opening_paragraph("supervisor"),
    "John demonstrated exceptional leadership...",
    generator.get_national_importance_paragraph(),
    generator.get_prong3_paragraph(),
    "I strongly support approval of this petition.",
]

filepath = generator.create_document(
    recommender_name="Jane Smith",
    recommender_title="VP of Engineering",
    recommender_org="TechCorp Inc.",
    recommender_email="jane@example.com",
    relationship="supervisor",
    paragraphs=paragraphs,
)
```

**CLI:**
```bash
python lor_generator.py \
    --persona executive \
    --beneficiary "John Doe" \
    --recommender "Jane Smith" \
    --title "VP of Engineering" \
    --org "TechCorp Inc." \
    --email "jane@example.com" \
    --relationship supervisor \
    --field cybersecurity
```

### 2. Personal Statement Generator

Gera Personal Statements com estrutura de 5 seções obrigatórias.

**Seções:**
1. Overview of the Proposed Endeavor
2. National Importance of the Endeavor (Prong 1)
3. Practical Impact and Innovation
4. Why I Am Well-Positioned (Prong 2)
5. Conclusion (com declaração de perjúrio)

**Exemplo:**
```python
from ps_generator import PSGenerator

generator = PSGenerator(
    beneficiary_name="John Doe",
    field="cybersecurity",
)

sections = {
    "overview": "My proposed endeavor is to advance...",
    "national_importance": "The United States has identified...",
    "practical_impact": "My work has resulted in...",
    "well_positioned": "I am uniquely qualified because...",
    "conclusion": "In summary, I respectfully submit...",
}

filepath = generator.create_document(sections=sections)
```

### 3. Package Builder

Constrói packages USCIS organizados por exhibits (paradigma Musheng).

**Exhibits (A-M):**
- A: Forms (I-140, ETA-9089, G-1145)
- B: Brief (Cover letter, TOC, Personal Statement)
- C: Self Petitioner Info (CV, diplomas)
- D: Critical Role (LORs)
- E: High Salary Evidence
- F: Memberships
- G: Judging Work of Others
- H: Acknowledgements
- I: Recognition
- J: Job Offers
- K: Media Coverage
- L: Original Contributions
- M: Supporting Research

**Exemplo:**
```python
from package_builder import PackageBuilder

builder = PackageBuilder(
    beneficiary_name="John Doe",
    case_type="EB-2 NIW",
)

# Adicionar documentos
builder.add_document("A", "/path/to/i-140.pdf", "Form I-140")
builder.add_document("D", "/path/to/lor1.pdf", "LOR from Dr. Smith")
builder.add_document("D", "/path/to/lor2.pdf", "LOR from Prof. Jones")
builder.add_document("L", "/path/to/publications.pdf", "Publications")

# Construir package
filepath = builder.build()
```

**CLI:**
```bash
# Listar estrutura de exhibits
python package_builder.py exhibits

# Merge rápido de PDFs
python package_builder.py merge file1.pdf file2.pdf --output merged.pdf

# Converter imagens para PDF
python package_builder.py convert img1.jpg img2.png --output images.pdf
```

## Regras Importantes

### Proibido em todos os documentos:
- Em-dash (—) - usar vírgulas ou dois pontos
- "I am writing to recommend..."
- Superlativos vazios (brilliant, extraordinary)
- Templates detectáveis

### Obrigatório:
- Variação entre cartas do mesmo caso
- Footnotes com Executive Orders
- Prong 3 (Matter of Dhanasar) em LORs
- Declaração de perjúrio em Personal Statements

## Fields Disponíveis

Para `field` parameter:
- `cybersecurity`
- `ai_ml`
- `clean_energy`
- `stem_education`
- `biotech`
- `semiconductor`
- `healthcare`

Cada field inclui automaticamente:
- Executive Orders relevantes
- Estatísticas de escassez
- Fontes oficiais nos footnotes
