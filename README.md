# Camera Studio

Aplicativo de câmera ao vivo desenvolvido em Python, com interface web local para ajustes de imagem, modo automático, zoom, acompanhamento facial, gravação da câmera e integração opcional com câmera virtual do OBS Studio.

O Camera Studio foi criado para oferecer uma visualização simples e estável da câmera, permitindo aplicar ajustes leves em tempo real sem depender de serviços externos.

## Funcionalidades

O aplicativo permite ligar a câmera diretamente pelo navegador e visualizar a imagem ao vivo em uma interface local.

Entre os recursos disponíveis estão:

- Visualização da câmera em tempo real;
- Ajuste de brilho;
- Ajuste de contraste;
- Ajuste de saturação;
- Ajuste de exposição;
- Espelhamento horizontal da câmera;
- Zoom manual;
- Modo automático de iluminação;
- Zoom automático baseado no tamanho do rosto;
- Acompanhamento facial;
- Gravação da imagem da câmera;
- Salvamento das gravações na pasta `Downloads`;
- Modo para preencher toda a janela do aplicativo com a câmera;
- Integração opcional com a câmera virtual do OBS Studio;
- Salvamento automático das configurações.

## Modo câmera em toda a janela

O botão **Preencher câmera** transforma o aplicativo em uma visualização dedicada da câmera.

Quando o botão é acionado:

- o cabeçalho desaparece;
- os ajustes leves desaparecem;
- os botões principais desaparecem;
- a etiqueta **CÂMERA AO VIVO** desaparece;
- a imagem da câmera ocupa toda a janela do aplicativo;
- o aplicativo não ativa o modo tela cheia do sistema operacional;
- a câmera continua funcionando normalmente;
- a gravação e os ajustes automáticos continuam ativos caso já tenham sido iniciados.

Para retornar à interface normal, utilize o botão discreto **Voltar ao modo normal** exibido sobre a imagem da câmera.

## Requisitos

- Python 3.10 ou superior;
- Uma câmera compatível com o sistema operacional;
- Navegador compatível com a API `getUserMedia`, como Google Chrome, Chromium, Microsoft Edge ou Firefox;
- OpenCV e NumPy para os recursos de detecção facial;
- O arquivo `haarcascade_frontalface_default.xml` para utilizar o acompanhamento facial e o zoom automático;
- OBS Studio e OBS Virtual Camera, caso a câmera virtual seja utilizada.

## Estrutura do projeto

```text
CameraStudio/
├── camera_app.py
├── camera_config.json
├── haarcascade_frontalface_default.xml
└── requirements.txt
