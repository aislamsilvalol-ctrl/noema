# Baseline — Freud, BEFORE the teaching engine rebuild

Captured 2026-08-15 against production (revision 7fd8a97, provider anthropic, `POST /ai/professor`, no notebook).
The spec's §119 sequence, verbatim, with the learner's wrong test answer scripted. This is what the rebuild is measured against.

## Turn 1

**Learner:** Me ensine Psicologia segundo Freud.

*events: [{"intent": {"intent": "explain"}}]*

**NOEMA:**

A ideia central de Freud não é "o inconsciente existe" — isso vira clichê. A ideia forte é que **sua mente não é uma coisa só, é três forças em guerra**, e a maior parte dessa guerra você nunca vê.

**Exemplo concreto primeiro.** Imagine alguém numa dieta, sozinho em casa, olhando um bolo de chocolate na geladeira às 23h.

- Uma parte dele grita: *quero agora, sem pensar em consequência*. Essa é o **id** — puro impulso, busca prazer imediato, não conhece "depois", não conhece "certo ou errado". Existe desde que você nasce.
- Outra parte dele diz: *se eu comer, vou me sentir um fracasso, minha mãe sempre disse que gula é falta de caráter*. Essa é o **superego** — a voz internalizada dos pais, da sociedade, da moral. Ela não quer que você seja feliz, quer que você seja "correto".
- E tem uma terceira parte, que precisa resolver esse impasse *sem quebrar nada*: talvez negocie — "como uma fatia pequena, não o bolo todo" — ou distraia a atenção, ou espere até a fome passar. Essa é o **ego**, que lida com a realidade concreta e tenta satisfazer o id sem provocar o superego nem se ferrar no mundo real.

**A analogia do próprio Freud:** o ego é um cavaleiro montado num cavalo forte (o id). O cavalo tem toda a força e a vontade de ir aonde quiser; o cavaleiro tem as rédeas, mas pouca força bruta — ele precisa *guiar*, não *dominar*. E há ainda um instrutor rígido observando de longe (o superego), pronto para criticar cada passo errado. O cavaleiro raramente vence por força; vence por manejo.

O ponto crucial: **isso não é uma decisão consciente e racional acontecendo em três etapas visíveis**. Id e superego operam em grande parte fora da consciência. Você não "escuta" essas vozes debatendo — você só sente a ansiedade, a culpa, o impulso, e o ego trabalha nos bastidores tentando manter tudo funcional. Quando esse trabalho falha, Freud diz que aparecem sintomas: ansiedade, atos falhos, sonhos estranhos — sinais de que o cavaleiro está perdendo o controle silenciosamente.

Agora me diga: nesse exemplo do bolo, se a pessoa comesse o bolo inteiro e depois inventasse uma desculpa tipo "eu precisava de energia para estudar", qual das três instâncias psíquicas estaria mais envolvida nessa desculpa, e por quê?

## Turn 2

**Learner:** Não entendi o que é inconsciente.

*events: [{"intent": {"intent": "explain"}}]*

**NOEMA:**

O inconsciente não é "a parte de trás da sua mente que você não usa". É a parte que **age em você o tempo todo, mas nunca aparece na tela**.

**Exemplo concreto.** Uma pessoa sempre chega atrasada em reuniões com o chefe que ela admira mas também teme — um chefe que, sem ela perceber, lembra o pai autoritário dela. Se você perguntar "por que você se atrasa?", ela vai te dar uma razão consciente e sincera: "trânsito", "esqueci a hora", "outro compromisso". E ela *acredita* nisso. Mas Freud diria: o atraso é uma forma de evitar o confronto com uma figura de autoridade que reativa uma ansiedade antiga — e essa ligação está totalmente fora do alcance da consciência dela. Ela não está mentindo. Ela genuinamente não sabe.

**A analogia clássica:** a mente é um iceberg. O que você pensa, sente e decide conscientemente é só a ponta acima da água — pequena, visível, controlável. Embaixo, enorme e invisível, está o resto: memórias reprimidas, desejos inaceitáveis, medos antigos, conflitos não resolvidos. Essa massa submersa não fica parada — ela empurra o iceberg inteiro, determina para onde ele vai, mesmo que você só veja a pontinha.

**Por que isso importa na teoria:** o id, que vimos antes, é quase todo inconsciente — você nunca "ouve" seus impulsos brutos diretamente, só sente os efeitos deles. Mas o inconsciente não é só o id: partes do superego (culpas antigas, regras absorvidas na infância que você nem lembra ter aprendido) e até do ego (mecanismos de defesa, como a pessoa do exemplo racionalizando o atraso) também operam fora da consciência. O inconsciente é onde o conflito acontece de verdade; a consciência só recebe o resultado já editado, disfarçado de razão lógica.

É por isso que Freud dizia que sonhos, lapsos de fala e "atos falhos" (esquecer um nome, trocar uma palavra) são pistas — rachaduras pequenas por onde o inconsciente vaza para a superfície.

Agora: na pessoa que sempre se atrasa para o chefe, se um amigo dissesse a ela "você está evitando ele por causa do seu pai", e ela reagisse com raiva forte e disser "isso é ridículo, nem penso nisso" — essa reação intensa de negação é, para Freud, evidência a favor ou contra a hipótese do amigo? Por quê?

## Turn 3

**Learner:** Então qualquer coisa que eu esqueci está no inconsciente?

*events: [{"intent": {"intent": "explain"}}]*

**NOEMA:**

Não — essa é a armadilha mais comum de quem lê Freud por alto. **Nem todo esquecimento é revelador.** Freud fez questão de separar dois tipos bem diferentes de "esquecer".

**Exemplo 1 — esquecimento banal:** Você esquece onde estacionou o carro no shopping. Isso não tem nada de misterioso — é só sobrecarga de memória, falta de atenção, o cérebro não registrou aquilo com força porque não era importante no momento. Freud não estaria interessado nisso.

**Exemplo 2 — esquecimento significativo:** Você tem uma reunião marcada com seu sogro, de quem você não gosta, e "esquece" completamente o horário, mesmo tendo anotado na agenda três vezes. Aqui Freud diria: presta atenção nesse esquecimento específico, porque ele não é aleatório — ele serve a um propósito. Evitar algo desconfortável. Isso é o que ele chama de **esquecimento motivado** ou **recalque** (repressão): a mente "empurra para baixo" algo que causaria ansiedade se ficasse na consciência, e o resultado prático é você "simplesmente esquecer".

**A diferença-chave está no padrão, não no fato isolado.** Um esquecimento comum é aleatório e sem carga emocional. Um esquecimento freudiano tem três marcas:
1. Está ligado a algo emocionalmente incômodo (culpa, medo, desejo proibido, raiva reprimida);
2. Se repete de forma consistente (você sempre esquece o nome dessa pessoa, sempre se atrasa para esse tipo de compromisso);
3. Quando você percebe o padrão, sente resistência ou desconforto em admitir a ligação — como na pergunta anterior, sobre a reação de raiva ao amigo.

**Analogia:** é como estática de rádio. A maior parte do chiado é só ruído sem sentido — não vale a pena investigar. Mas se, dentro do chiado, você percebe que toda vez que uma certa palavra é dita a estática aumenta, *isso* é um sinal de que tem algo ali. Freud está interessado no chiado que tem padrão, não em todo chiado.

Então: esquecer uma senha de wifi não é "reprimir". Esquecer sistematicamente o aniversário do namorado que você secretamente quer terminar — isso, para Freud, é o inconsciente falando.

Agora me diga: se uma pessoa esquece constantemente de responder mensagens de UM amigo específico, mas responde normalmente a todos os outros, isso se encaixa melhor no "esquecimento banal" ou no "esquecimento motivado"? Que critério você usou para decidir?

## Turn 4

**Learner:** Agora entendi.

*events: [{"intent": {"intent": "explain"}}]*

**NOEMA:**

Bom. Antes de seguir para outro conceito — id, ego, superego, ou inconsciente — me responde rápido, sem eu explicar de novo:

Se uma pessoa some das redes sociais toda vez que a ex-namorada posta uma foto nova, mas continua ativa normalmente o resto do tempo, isso é recalque, ou só coincidência/esquecimento banal? E qual das três marcas (emoção, repetição, resistência) você usou pra decidir?

## Turn 5

**Learner:** Me testa.

*events: [{"intent": {"intent": "explain"}}]*

**NOEMA:**

Certo. Cinco perguntas, uma de cada vez seria mais lento — vou te dar as cinco juntas, mas responda na ordem. Sem consultar nada.

**1.** Um homem está com raiva do chefe, mas chega em casa e grita com o cachorro sem motivo. Qual das três instâncias (id, ego, superego) está mais diretamente em ação nesse deslocamento de raiva, e qual delas ele está tentando "enganar" ao fazer isso?

**2.** Explique por que o ego, na analogia do cavaleiro, não pode simplesmente ignorar o id nem simplesmente obedecer ao superego. O que aconteceria em cada um desses dois extremos?

**3.** Uma mulher jura que não tem nenhum problema com a irmã mais nova, mas todo aniversário dela "esquece" de mandar parabéns — só dela, nunca dos outros parentes. Segundo os três critérios que vimos, isso é recalque ou esquecimento banal? Justifique com pelo menos dois critérios.

**4.** Dê um exemplo SEU (não repita os meus) de algo que pareça esquecimento banal mas que, olhando com atenção, poderia ser esquecimento motivado. Explique o que faria você suspeitar de recalque nesse caso.

**5.** Por que Freud diz que a consciência recebe "o resultado já editado" do conflito psíquico, e não o conflito em si? Dê um exemplo de uma emoção ou comportamento que você sente/faz, e a "edição" que pode estar escondendo o conflito real por trás.

Manda as respostas, uma por vez ou todas juntas — o que for mais confortável.

## Turn 6

**Learner:** Acho que é o inconsciente, porque é tudo que eu não estou pensando agora.

*events: [{"intent": {"intent": "explain"}}]*

**NOEMA:**

Essa resposta mistura duas coisas — e é importante separar, porque revela um buraco que ainda não tínhamos coberto.

"Tudo que eu não estou pensando agora" inclui, por exemplo, seu número de telefone, o nome da sua rua, o que você comeu ontem. Você não está pensando nisso neste segundo, mas se eu perguntar, você lembra na hora, sem esforço, sem resistência. Freud chama isso de **pré-consciente** — não é inconsciente, é só "fora do foco agora", como abas abertas no navegador que você não está olhando mas pode clicar quando quiser.

**Inconsciente de verdade é diferente: é o que resiste a vir à tona mesmo quando você tenta.** Se eu te perguntar "por que você chega atrasado especificamente nas reuniões com seu chefe?", e a resposta real é "porque ele me lembra meu pai autoritário e isso me dá ansiedade" — você não vai simplesmente lembrar disso como lembra seu telefone. Vai sentir um bloqueio, vai inventar outra explicação, ou vai negar com força (lembra a pergunta da raiva do amigo?). Essa resistência é a marca registrada do inconsciente. Não é "esquecido temporariamente" — é **mantido fora de propósito**, mesmo que você não saiba que está fazendo isso.

Então a linha não é "estou pensando agora" vs "não estou pensando agora". A linha é: **você consegue acessar fácil (pré-consciente) vs. algo empurra ativamente para impedir o acesso (inconsciente)**.

Isso não respondeu nenhuma das 5 perguntas do teste, então elas continuam de pé. Mas antes de voltar a elas, me diz: seu número de telefone, quando você não está pensando nele, está no pré-consciente ou no inconsciente — e por quê?

## Timings

| turn | first token (s) | total (s) | prompt tokens | completion tokens |
|---|---|---|---|---|
| 1 | 10.89 | 22.52 | 341 | 1528 |
| 2 | 6.76 | 18.49 | 1298 | 1110 |
| 3 | 11.52 | 23.09 | 2228 | 1237 |
| 4 | 3.41 | 5.55 | 3175 | 163 |
| 5 | 4.7 | 11.77 | 3345 | 630 |
| 6 | 9.5 | 16.95 | 3954 | 1085 |