# Camera Studio

Aplicativo de câmera ao vivo desenvolvido em Python, com interface web local para ajustes de imagem, modo automático, zoom, acompanhamento facial, gravação da câmera e integração opcional com câmera virtual do OBS.

## Recursos

O Camera Studio permite ligar a câmera diretamente pelo navegador e visualizar a imagem ao vivo em uma interface simples. O aplicativo oferece ajustes leves e instantâneos de brilho, contraste, saturação, exposição, espelhamento e zoom.

Também é possível ativar o modo automático de iluminação. Nesse modo, o aplicativo analisa suavemente a luminosidade da imagem e ajusta brilho, contraste e exposição sem bloquear a câmera nem enviar continuamente os frames completos para o backend.

O aplicativo possui zoom automático e acompanhamento facial opcionais. Quando ativados, eles utilizam o detector facial para ajudar a manter o rosto enquadrado. O comportamento normal do zoom é suave e limitado, evitando alterações bruscas, tremores e saltos repentinos entre o zoom máximo e o mínimo.

Há ainda um modo de preenchimento da câmera. Ao clicar em **Preencher câmera**, toda a interface do aplicativo desaparece e a imagem da câmera ocupa toda a janela do Camera Studio. O aplicativo não solicita o modo tela cheia do sistema. Para retornar, basta clicar em **Voltar ao modo normal**.

## Requisitos

- Python 3.10 ou superior;
- Uma câmera compatível com o sistema operacional;
- Navegador com suporte a `getUserMedia`, como Google Chrome, Chromium, Microsoft Edge ou Firefox;
- O arquivo do classificador facial `haarcascade_frontalface_default.xml` para utilizar o acompanhamento facial;
- OBS Studio e OBS Virtual Camera, caso a função de câmera virtual seja utilizada.

## Estrutura do projeto

```text
CameraStudio/
├── camera_app.py
├── camera_config.json
├── haarcascade_frontalface_default.xml
└── requirements.txt
