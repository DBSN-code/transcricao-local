# Transcrição Local

Aplicativo nativo para macOS que transcreve áudios do WhatsApp Web no próprio
Mac, usando o **SpeechAnalyzer/SpeechTranscriber da Apple**. Uma janela e um
ícone na barra de menus permitem iniciar e parar o servidor, acompanhar seu
estado e escolher se ele deve iniciar ao entrar no Mac.

O app oferece um endereço local compatível com o formato de transcrição da
OpenAI para a extensão **WA Plus a Mais**. Não precisa de chave de API e não
envia os áudios a um serviço de transcrição na nuvem.

## Download e requisitos

**[Baixar o instalador para Mac](https://github.com/DBSN-code/transcricao-local/releases/latest)**

- Mac com chip **Apple M1 ou superior**.
- **macOS 27 ou superior** para o instalador 1.1.0.
- Chrome e a extensão WA Plus a Mais, instalada separadamente.
- Internet para baixar o modelo de português da Apple, caso ainda não esteja instalado.

Python, FFmpeg e o servidor acompanham o aplicativo. Quem instala pelo `.dmg`
não precisa de Python, Homebrew, FFmpeg ou Xcode no computador.

Este repositório contém o app e o servidor local. A extensão do Chrome é um
projeto separado e não acompanha este código nem o instalador.

## Instalar e usar

1. Baixe `Transcricao-Local-1.1.0-arm64.dmg` na página de versões.
2. Abra o disco e arraste **Transcrição Local** para **Aplicativos**.
3. Ejete o disco e abra a cópia de Transcrição Local em Aplicativos.
4. Se aparecer **Preparar português**, clique e aguarde **Português disponível**.
5. Clique em **Iniciar servidor** e depois em **Testar transcrição**.
6. Configure a extensão conforme a tabela abaixo.

Também é possível instalar na pasta Aplicativos do seu usuário, sem acesso
de administrador. O app precisa ser copiado antes de iniciar o servidor;
não o execute diretamente do disco de instalação.

O modelo de transcrição é separado do modelo de texto do Apple Intelligence.
A preparação acontece pelo app, sem exigir ativar Apple Intelligence, Siri
ou Ditado nos Ajustes. Após o download do modelo, a transcrição funciona
localmente sem internet; o WhatsApp Web continua precisando de conexão.

### Autorização do macOS

Esta versão tem assinatura local e **ainda não está notarizada pela Apple**.
Ao receber o arquivo pela internet, o macOS pode impedir a primeira abertura.
Se você conhece e confia neste projeto, após tentar abrir o app acesse
**Ajustes do Sistema → Privacidade e Segurança → Abrir Mesmo Assim** para
autorizar esse aplicativo. Não desative as proteções globais do Mac.

Consulte a [orientação oficial da Apple](https://support.apple.com/pt-br/102445).
Na página da versão, `SHA256.txt` permite conferir a integridade do instalador.

## Configurar a extensão

No Chrome, abra a seção **Transcrição de áudio** da extensão e preencha:

| Campo | Valor |
| --- | --- |
| Serviço de transcrição | Servidor compatível com OpenAI |
| Endereço do servidor | `http://127.0.0.1:5092/v1` |
| Modelo | `apple-speechanalyzer` |
| Chave do servidor | Deixe em branco |
| Idioma do áudio | Português |

Clique em **Salvar configuração** e use o botão de transcrição em um áudio
do WhatsApp Web. O instalador não instala nem modifica a extensão.

## Controles do aplicativo

- **Iniciar servidor / Parar servidor:** muda o funcionamento atual. Durante
  uma transcrição, aguarde terminar para solicitar a parada.
- **Iniciar o servidor ao entrar no Mac:** preferência independente de
  iniciar ou parar agora; inicia o servidor, sem abrir a janela.
- **Testar transcrição:** usa uma mensagem sintética incluída no app, sem
  precisar de microfone ou gravação pessoal.
- **Copiar endereço / modelo:** ajuda a configurar a extensão.
- **Abrir WhatsApp:** abre o WhatsApp Web no Chrome.

Fechar a janela mantém o ícone na barra de menus. **Sair do aplicativo**
fecha a interface e mantém o servidor no estado atual. Para interromper
as transcrições, use **Parar servidor**.

## Privacidade e limites

- O servidor escuta somente em `127.0.0.1`, sem acesso pela rede local.
- Solicitações de páginas web comuns e nomes de host externos são rejeitadas.
- Áudios OGG/Opus, WebM, WAV, M4A, MP3 e FLAC são convertidos localmente.
- Até **25 MB** e **30 minutos** por arquivo, um áudio por vez, com até
  170 segundos de conversão/transcrição. Áudios maiores são rejeitados.
- Português do Brasil é o padrão. Não há detecção automática de idioma.
  Outros idiomas exigem seus modelos instalados no macOS.
- Não há fallback para transcrição na nuvem.
- Arquivos temporários são removidos ao concluir ou falhar. O servidor não
  salva áudios nem transcrições em logs. A extensão pode manter seu próprio resultado.
- O app distribuído guarda estado técnico e logs em
  `~/Library/Application Support/Transcricao Local`.

O instalador inclui apenas um áudio sintético de teste. Não inclui conversas,
gravações pessoais, configurações do Chrome nem chaves de API.

## Atualizar ou remover

Antes de substituir ou mover o app, **pare o servidor, desative o início
automático e saia do aplicativo**. Depois copie a nova versão e abra novamente.
Se uma versão antiga ainda controla o serviço, faça esses passos nela primeiro.

Para remover, faça os mesmos passos e mova o aplicativo para o Lixo. A pasta
de suporte contém somente dados técnicos e pode ser removida separadamente.

## Desenvolvimento

O código está organizado assim:

| Arquivo | Responsabilidade |
| --- | --- |
| `NativeApp.swift` | Janela e barra de menus nativas, em SwiftUI |
| `SpeechWorker.swift` | Modelo de transcrição da Apple e preparação de idioma |
| `server.py` | Endpoint local `/v1/audio/transcriptions` |
| `manage.py` | Estado, início/parada e regra de início de sessão |
| `runtime_paths.py` | Recursos do app e dados graváveis do usuário |
| `backend_entry.py` | Entrada do servidor e controlador empacotados |
| `packaging/` | Construção e verificação do instalador |

### Executar a partir do código

Use um Mac com Apple Silicon, macOS 27 e ferramentas de desenvolvimento Apple
com SDK de macOS 27 e compilador Swift compatível. Instale Python para o
desenvolvimento; ele não é necessário para quem recebe o instalador.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
mkdir -p bin
xcrun swiftc -O -parse-as-library SpeechWorker.swift -o bin/speech-worker
.venv/bin/python manage.py models --json
.venv/bin/python manage.py prepare-model --json
.venv/bin/python manage.py start
```

Comandos de controle:

```sh
.venv/bin/python manage.py status
.venv/bin/python manage.py stop
.venv/bin/python manage.py autostart on
.venv/bin/python manage.py autostart off
```

`Iniciar.command`, `Parar.command` e `Desativar.command` são atalhos para o
ambiente de desenvolvimento. `build_app.py` gera uma interface local em
`build/TranscricaoLocal.app`, vinculada a esta pasta; mantenha a pasta no
mesmo lugar enquanto usar essa variante. O instalador distribuído é portátil
e não depende da pasta do projeto.

```sh
.venv/bin/python build_app.py
.venv/bin/python -m unittest test_server test_manage test_runtime_paths
```

### Reconstruir o instalador 1.1.0

A distribuição foi construída com Python 3.14.7 para ARM64, instalado pelo
Homebrew, PyInstaller 6.22.3 e FFmpeg 9.0.2. A coleta de licenças em
`build_release.py` usa a estrutura do Python do Homebrew. O conversor FFmpeg
é compilado das fontes oficiais, apenas com codecs de áudio e sem rede ou
componentes GPL/nonfree.

Prepare as fontes e os ambientes de desenvolvimento:

```sh
mkdir -p build/vendor
curl -fL https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz \
  -o build/vendor/ffmpeg-9.0.2.tar.xz
printf '%s  %s\n' \
  '8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e' \
  'build/vendor/ffmpeg-9.0.2.tar.xz' | shasum -a 256 -c -
tar -xf build/vendor/ffmpeg-9.0.2.tar.xz -C build/vendor
python3.14 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements-build.txt
```

Com `.venv` preparado conforme a seção anterior:

```sh
.venv/bin/python build_app.py
sh packaging/build_ffmpeg.sh
.build-venv/bin/python packaging/build_release.py
.venv/bin/python packaging/verify_release.py
.venv/bin/python -m unittest test_server test_manage test_runtime_paths
```

A construção usa a voz do sistema **Luciana (Português (Brasil))** para gerar
o áudio sintético de teste; essa voz precisa estar disponível no Mac de
desenvolvimento. O Mac de destino usa o áudio já incluído e não precisa da voz.

O resultado fica em `dist/`, com o `.dmg`, as instruções, a soma SHA-256 e o
relatório de verificação. Ferramentas de ícones e montagem de discos precisam
das permissões normais de desenvolvimento do macOS.

## Verificação e limitações conhecidas

Os **21 testes** do servidor, controle de serviço e localização de recursos
passaram no Mac de desenvolvimento. O instalador foi montado somente para
leitura, copiado para um caminho com espaços e acentos e testado após ejetar
o disco, com `PATH` limitado às ferramentas do sistema.

Foram verificadas as assinaturas locais, 51 dependências binárias e
transcrições de WAV, OGG e WebM sintéticos. O relatório dessa distribuição
está em [docs/verification-1.1.0.json](docs/verification-1.1.0.json).

Ainda precisam de confirmação em um computador de destino: instalação em
um segundo Mac, autorização após download pela internet, primeiro download
do modelo, início após login/reinicialização e áudio real do WhatsApp.
Os testes locais não comprovam essas condições.

## Componentes e referências

As fontes do FFmpeg, sua receita de compilação e as licenças dos componentes
acompanham o app em `Contents/Resources/Sources` e `Contents/Resources/Licenses`.
Python, PyInstaller e FFmpeg são componentes separados, com suas próprias
licenças. A publicação pública deste código não define uma licença adicional
para o código próprio do projeto.

- [SpeechAnalyzer e SpeechTranscriber — Apple](https://developer.apple.com/videos/play/wwdc2025/277/)
- [Download dos modelos — Apple AssetInventory](https://developer.apple.com/documentation/speech/assetinventory)
- [Formato de transcrição de áudio — OpenAI](https://developers.openai.com/api/docs/guides/speech-to-text)
- [FFmpeg](https://ffmpeg.org/)
- [PyInstaller](https://pyinstaller.org/)
- [imageio-ffmpeg, usado no ambiente de desenvolvimento](https://github.com/imageio/imageio-ffmpeg)
