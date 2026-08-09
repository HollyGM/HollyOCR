# Compilação do HollyOCR

## macOS Apple Silicon

Pré-requisitos:

- macOS 12 ou superior;
- Python 3.12 arm64 em `.venv`;
- Poppler, Tesseract e idiomas do Tesseract;
- `mavis-trash`, usado para limpar builds anteriores de forma recuperável.

```bash
brew install python@3.12 poppler tesseract tesseract-lang mavis-trash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-macos-lock.txt
./build_mac.sh
```

O resultado fica em `dist/HollyOCR.app`. O script valida Python, arquitetura arm64, testes, análise estática, identificador do bundle, assinatura, tamanho e hash do aplicativo.

O build local usa assinatura ad hoc. Distribuição pública sem o aviso do Gatekeeper exige uma conta Apple Developer, certificado Developer ID Application e notarização.

## Windows

Execute `build_exe.bat` em um Windows com Python 3.12. Tesseract não é incorporado automaticamente. Uma pasta local de Poppler pode ser colocada em `bin/poppler` para inclusão no pacote.

## Linux

O núcleo e a interface são compatíveis com Linux quando Python/Tk, Poppler e Tesseract estão instalados. Não há, nesta versão, um empacotador oficial AppImage, Flatpak ou pacote de distribuição.

## Arquiteturas

- macOS: o build oficial atual é arm64, adequado a Apple Silicon.
- Windows: o executável deve ser gerado no próprio Windows.
- Linux: o pacote deve ser gerado e testado na distribuição de destino.

O PyInstaller não produz builds confiáveis para outro sistema operacional por compilação cruzada.
