# Histórico de versões

Todas as mudanças relevantes do HollyOCR são registradas neste arquivo.

## 5.1.0 (build 5) — 2026-11-16

### Corrigido

- **PDFs protegidos só contra alterações** (criptografia AES, abrem sem senha) não convertiam no aplicativo para macOS, nem com OCR: o app empacotado usa só o `pypdf`, e faltava a biblioteca `cryptography`, de que ele precisa para decifrar AES. Ela agora faz parte das dependências. PDFs com **senha de abertura** passam a ser recusados com a mensagem "PDF protegido por senha de abertura…", em vez de "PDF sem páginas legíveis, vazio, protegido ou corrompido".
- O progresso do OCR, que contém o texto integral das páginas já lidas, ficava em `.hollyocr_checkpoints/`, dentro da pasta de saída (que pode estar no iCloud, no Dropbox ou compartilhada), sem prazo de remoção. Agora fica na pasta de dados do aplicativo, com acesso só do usuário, e expira em 30 dias. A pasta antiga é apagada quando o mesmo arquivo é convertido de novo.
- Com a pasta de saída dentro da pasta de entrada, as conversões anteriores (`.md`) eram tratadas como documentos novos. Agora a pasta de saída é ignorada na busca.
- Os programas auxiliares (`pdftoppm`, `tesseract`) não são mais procurados na pasta atual, onde um executável plantado teria prioridade sobre o Poppler instalado.

### Segurança

- `pypdf` 6.19.0 → 6.21.4: corrige 18 alertas (10 altos) publicados entre 21 e 30 de outubro de 2026, como laços infinitos e consumo excessivo de memória em PDFs malformados.
- `Pillow` 12.3.0 → 13.0.0: corrige 62 alertas (5 críticos, 24 altos) publicados entre 19 de outubro e 12 de novembro de 2026, em leitores de TIFF, BMP, APNG e outros formatos.
- No OCR por Tesseract, o Pillow abre só JPEG e PNG. Antes ele identificava o formato pelo conteúdo, e um arquivo `.jpg` disfarçado chegava a leitores de outros formatos.
- `setuptools` 84.0.0 → 84.2.1 no ambiente de build (alerta baixo, só Windows).
- A verificação do GitHub, que inclui o `pip-audit`, passa a rodar também uma vez por mês.

### Novo

- **TIFF**: cada página de uma digitalização com várias páginas é lida por OCR, inclusive TIFF de 16 bits.
- **HEIC/HEIF** (fotos do iPhone): convertidas pelo próprio macOS (`sips`) e lidas por OCR. Em outros sistemas, a conversão é recusada com aviso.
- No OCR da Apple, todos os idiomas escolhidos são usados (`por+eng` reconhece português e inglês). Antes só o primeiro valia.

### Testes

- 97 testes e 15 subtestes, incluindo PDFs protegidos (do jeito que o app empacotado lê), arquivos disfarçados, TIFF multipágina e de 16 bits, HEIC, local e prazo do progresso salvo, busca de programas auxiliares e pasta de saída dentro da entrada. O progresso salvo nos testes vai para uma pasta temporária.

## 5.0.1 (build 4) — 2026-10-02

### Corrigido

- A combinação de texto nativo e OCR deixa de eliminar linhas apenas por semelhança. Valores, datas, nomes, negações e associações entre células são preservados quando diferem; a remoção de duplicações exige correspondência do conteúdo.
- DOCX mantém a ordem entre parágrafos e tabelas, extrai tabelas aninhadas e tabelas de cabeçalhos/rodapés, evita duplicações de células mescladas e preserva colunas vazias.
- Extrações PDF com quantidade de páginas divergente e falhas de renderização ou OCR são identificadas como falhas, sem gerar uma saída apresentada como completa. Páginas de uma extração parcial não são misturadas com um segundo extrator que reinicie a numeração.
- Falhas de OCR preservam os checkpoints das páginas concluídas para retomada. Checkpoints de versões anteriores são invalidados para aplicar as novas regras de preservação.
- O cancelamento é conferido entre páginas de extração e OCR. Fechar a janela aguarda o encerramento do processamento e a gravação do progresso. A interface informa o cancelamento sem levar a barra artificialmente a 100%; Ctrl+C na linha de comando encerra com código 130.
- Seletores de formato, idioma, DPI e agrupamento mantêm opções restritas após uma conversão. O agrupamento escolhido é salvo e opções inválidas não podem produzir uma conclusão sem arquivo.
- A validação de dependências considera o mecanismo OCR selecionado e verifica separadamente os idiomas combinados do Tesseract.
- A compilação preserva artefatos anteriores em `.build_backups/` quando `mavis-trash` não está instalado.

### Ambiente macOS

- Python e Tk atualizados para 3.12.15, Poppler para 26.09.0 e Tesseract para 5.5.3. O aplicativo recompilado incorpora o Python atualizado; Poppler e Tesseract continuam externos.
- O build exige Python 3.12.15 ou patch posterior da mesma série. As dependências Python fixadas permanecem nas versões auditadas, sem vulnerabilidades conhecidas na consulta de 2 de outubro de 2026.

## 5.0.0 (build 3) — 2026-09-30

### Corrigido

- PDFs com fontes malformadas (vistos em exportações reais de sistemas de tribunais) que mapeiam um glifo para unidades de código UTF-16 soltas ("surrogates") não abortam mais a conversão do documento inteiro com `UnicodeEncodeError`. O texto extraído passa por `_drop_lone_surrogates`, que reagrupa pares adjacentes e substitui o que sobrar sem par. Cobertura em `test_native_extraction_repairs_lone_surrogate_from_broken_font`.

### Segurança

- `pypdf` 6.15.0 → 6.19.0. As versões intermediárias corrigem laços infinitos, consumo excessivo de memória e recuperação de FlateDecode em PDFs malformados, relevantes para um aplicativo que abre arquivos de terceiros. O piso em `pyproject.toml` e `hollyocr/requirements.txt` sobe para `>=6.19.0`.

### Dependências

- Atualizações de patch no ambiente de build do macOS (`requirements-macos-lock.txt`): `pyinstaller` 6.22.3, `pyinstaller-hooks-contrib` 2026.8, `pyobjc-*` 12.2.2, `lxml` 6.1.3, `packaging` 26.3 e `tqdm` 4.70.1.

### Documentado

- README: o número de build exibido estava desatualizado.

## 5.0.0 (build 2) — 2026-08-18

Correções decorrentes de uma auditoria de código interna. Sem mudanças de comportamento visíveis na interface.

### Corrigido

- A linha de comando (`hollyocr -i ... -o ...`, sem `--gui`) agora reaproveita um único pool de processos para todo o lote de arquivos, em vez de abrir e encerrar um pool novo a cada lote de páginas de OCR. Em documentos de milhares de páginas, isso evitava overhead real e, com o backend Apple Vision, o reaquecimento repetido do modelo a cada pool novo.
- A migração de configurações antigas não confia mais em um `user_settings.json` avulso na pasta atual de execução ou na pasta do script; só os locais oficiais e os nomes legados documentados são considerados.
- O instalador de dependências do Windows (`install_dependencies.ps1`) verifica o hash SHA-256 do Poppler antes de extraí-lo.

### Removido

- Interface CustomTkinter morta (`gui/modern_ctk/widgets.py`, `theme.py`, `scroll_patches.py`), inalcançável a partir do aplicativo em uso, e as dependências `customtkinter`/`tkinterdnd2` que só existiam para sustentá-la.

### Documentado

- README: o `HollyOCR.app` compilado usa apenas `pypdf` para extração nativa (PyMuPDF fica desativado por estabilidade dentro do binário do PyInstaller); `HOLLYOCR_ENABLE_PYMUPDF=1` reativa o PyMuPDF.

## 5.0.0 — 2026-08-08

### Adicionado

- Nova identidade HollyOCR e ícones para macOS, Windows e interface.
- Versionamento canônico com número de build.
- Metadados modernos de pacote e comandos `hollyocr`/`HollyOCR`.
- Testes de regressão para segurança de arquivos e Apple Vision.
- Documentação de compilação, segurança e contribuição.

### Alterado

- Pacote interno reorganizado como `hollyocr`.
- Interface redesenhada com identidade tecnológica e processamento local.
- Migração de `PyPDF2` para `pypdf` 6.
- Atualização das dependências com vulnerabilidades conhecidas.
- Limites coerentes para DPI, processos paralelos e limiar de OCR.

### Corrigido

- Imagens fornecidas pelo usuário não são mais excluídas por padrão.
- Exclusão temporária fica restrita à pasta temporária do sistema.
- Exceções dentro do silenciador do Apple Vision propagam corretamente.
- Medição de imagens continua funcionando com a API atual do `pypdf`.
- PDFs corrompidos são fechados corretamente após a análise, inclusive no Windows.
- Configurações são migradas e gravadas de forma atômica.

### Removido

- Identidade visual jurídica anterior.
- Módulos e documentação obsoletos de recursos de IA externa.
