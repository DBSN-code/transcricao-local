# Interface nativa de Transcrição Local

A direção visual é o próprio macOS, conforme pedido do usuário. A interface
opera um servidor existente e segue seus padrões de janela, controles e menus.

## Estrutura

- Janela única com estado do servidor e ação iniciar/parar no primeiro grupo.
- Preferência de início automático em grupo separado: não muda o funcionamento atual.
- Endereço e modelo copiáveis para a extensão.
- Teste local com mensagem sintética e retorno visível na mesma janela.
- Ícone permanente na barra de menus enquanto o aplicativo estiver aberto.
- Janela inicial de 610 × 700 pontos, redimensionável a partir de 570 × 650 pontos.

## Componentes

SwiftUI usa fonte de sistema, SF Symbols e cores semânticas nativas.
O título usa `title2` semibold; o estado, `headline`; as orientações, `callout`;
o rodapé, `caption`; endereço e modelo usam fonte monoespaçada e texto selecionável.
O Form agrupado e os controles padrão mantêm o foco de teclado do macOS.
Botões de copiar, atualizar e fechar aviso têm rótulos acessíveis.
A aparência acompanha a preferência do macOS, sem escolha fixa de cores.
Verde indica servidor ativo ou teste concluído; laranja indica erro ou conflito;
a cor de destaque do sistema identifica transcrição e a ação principal.
O estado combina texto e símbolo; sua informação nunca depende só da cor.
Iniciar/parar é um botão destacado; o início automático é um interruptor separado.
Copiar e atualizar são ações discretas com símbolo e descrição de ajuda.

Quando o português não estiver disponível, o primeiro grupo mostra a ação
“Preparar português”, com explicação do download inicial e do processamento
local. Durante a preparação, o botão mostra andamento e impede novas ações.
Esse estado reutiliza a hierarquia, os controles e as cores existentes.

O menu compartilha o mesmo estado e oferece abrir a janela, iniciar/parar,
início automático, copiar endereço, abrir WhatsApp no Chrome e sair do aplicativo.

## Estados e comportamento

O estado inicial é “Verificando servidor…” e impede controle até a primeira resposta.
Ativo, parado, iniciando, transcrevendo e indisponível têm mensagens distintas.
Durante iniciar/parar ou testar, mostrar andamento e impedir ações duplicadas.
Durante uma transcrição, “Parar servidor” fica desabilitado na janela e no menu;
o texto orienta esperar a conclusão e então solicitar a parada explicitamente.
Conflito aparece como indisponibilidade com a razão visível e impede controle:
uma resposta de `/health`, mesmo compatível, sem o serviço gerenciado pelo
aplicativo não autoriza iniciar ou parar o processo externo.
O início automático vale para a próxima entrada no Mac. Alterá-lo não inicia
nem para agora; iniciar/parar agora não muda essa preferência.
Fechar a janela mantém o menu. Sair do aplicativo não para o servidor.
O teste exige servidor ativo, sem transcrição em andamento e modelo de português
disponível. Mostra somente uma mensagem sintética, com resultado selecionável,
e não guarda histórico pessoal. Avisos aparecem na janela e podem ser fechados.

## Fontes executáveis

`NativeApp.swift` implementa a janela e o menu. `manage.py` controla o serviço e
o início automático. `server.py` mantém o contrato já usado pela extensão.
