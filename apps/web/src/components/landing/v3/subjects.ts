/**
 * What the later sections say once the visitor has named a subject.
 *
 * The hero's reply comes from the real tutor. The practice question, the
 * concept map and the review card that follow do not call a model — they
 * adapt locally: a few subjects have hand-written material, everything else
 * gets a template built from the words the visitor typed. Free text is the
 * rule; the three curated banks are just better than the template.
 */

import type { Locale } from '@/lib/i18n';

export interface SubjectBank {
  /** How the subject is named in later copy ("Practice Freud"). */
  label: string;
  /** The written lesson opening, used when the live tutor is unavailable. */
  sample: string;
  question: string;
  options: string[];
  /** Index into `options`. */
  correct: number;
  /** What the tutor says after a wrong answer: the distinction that matters. */
  correction: string;
  /** Concepts and mastery before/after the practice answer. */
  concepts: { name: string; before: number; after: number }[];
  card: { front: string; back: string };
}

type Bank = Record<Locale, SubjectBank>;

const FREUD: Bank = {
  pt: {
    label: 'Freud',
    sample:
      'Quase tudo em Freud parte de uma ideia: boa parte do que você faz vem de motivos que você não vê. Pense em chamar a namorada nova pelo nome da ex. Para Freud não é acaso — é o **inconsciente** deixando escapar um conflito que a pessoa não admite. Se alguém "esquece" um aniversário sem querer, que parte da mente fez o trabalho?',
    question: 'Você esquece onde deixou as chaves, mas lembra na hora quando alguém pergunta. Para Freud, isso está onde?',
    options: ['No inconsciente', 'No pré-consciente', 'No superego'],
    correct: 1,
    correction:
      'O critério não é "estou pensando nisso agora?". É: consigo trazer de volta com esforço normal, ou está bloqueado? As chaves voltaram fácil — pré-consciente. O inconsciente é o que resiste.',
    concepts: [
      { name: 'Inconsciente', before: 62, after: 66 },
      { name: 'Pré-consciente vs inconsciente', before: 48, after: 31 },
      { name: 'Id, ego, superego', before: 20, after: 20 },
    ],
    card: { front: 'Esquecimento que volta com uma dica é…', back: 'pré-consciente (não reprimido)' },
  },
  en: {
    label: 'Freud',
    sample:
      'Almost everything in Freud starts from one idea: much of what you do comes from motives you cannot see. Think of calling a new partner by an old name. For Freud that is not chance — it is the **unconscious** leaking a conflict the person will not admit. If a friend "forgets" a birthday without meaning to, which part of the mind did the work?',
    question: 'You forget where you left your keys, then remember the moment someone asks. For Freud, where was that memory?',
    options: ['In the unconscious', 'In the preconscious', 'In the superego'],
    correct: 1,
    correction:
      'The test is not "am I thinking about it now?". It is: can I bring it back with ordinary effort, or is it blocked? The keys came back easily — preconscious. The unconscious is what resists.',
    concepts: [
      { name: 'The unconscious', before: 62, after: 66 },
      { name: 'Preconscious vs unconscious', before: 48, after: 31 },
      { name: 'Id, ego, superego', before: 20, after: 20 },
    ],
    card: { front: 'Forgetting that returns with a hint is…', back: 'preconscious (not repressed)' },
  },
  es: {
    label: 'Freud',
    sample:
      'Casi todo en Freud parte de una idea: gran parte de lo que haces viene de motivos que no ves. Piensa en llamar a la pareja nueva por el nombre de la ex. Para Freud no es casualidad — es el **inconsciente** dejando escapar un conflicto que la persona no admite. Si alguien "olvida" un cumpleaños sin querer, ¿qué parte de la mente hizo el trabajo?',
    question: 'Olvidas dónde dejaste las llaves y lo recuerdas en cuanto alguien pregunta. Para Freud, ¿dónde estaba eso?',
    options: ['En el inconsciente', 'En el preconsciente', 'En el superyó'],
    correct: 1,
    correction:
      'El criterio no es "¿lo estoy pensando ahora?". Es: ¿puedo traerlo de vuelta con esfuerzo normal, o está bloqueado? Las llaves volvieron fácil — preconsciente. El inconsciente es lo que resiste.',
    concepts: [
      { name: 'El inconsciente', before: 62, after: 66 },
      { name: 'Preconsciente vs inconsciente', before: 48, after: 31 },
      { name: 'Ello, yo, superyó', before: 20, after: 20 },
    ],
    card: { front: 'Un olvido que vuelve con una pista es…', back: 'preconsciente (no reprimido)' },
  },
};

const ITALIAN: Bank = {
  pt: {
    label: 'italiano',
    sample:
      'Em italiano, quase toda palavra termina em vogal, e essa vogal carrega o gênero e o número. **Ragazzo** é um menino; **ragazzi**, vários; **ragazza**, uma menina. Você não decora regras — ouve o final. Então: *casa* é uma; como fica "casas"?',
    question: 'Como fica "as meninas" em italiano?',
    options: ['Le ragazze', 'Le ragazzi', 'La ragazze'],
    correct: 0,
    correction:
      'O artigo e o final mudam juntos: *la ragazza* → *le ragazze*. O -i é o plural masculino (*i ragazzi*). Ouça o par, não a palavra solta.',
    concepts: [
      { name: 'Vogais finais', before: 58, after: 64 },
      { name: 'Concordância artigo–substantivo', before: 40, after: 28 },
      { name: 'Presente do indicativo', before: 15, after: 15 },
    ],
    card: { front: 'la ragazza → (plural)', back: 'le ragazze' },
  },
  en: {
    label: 'Italian',
    sample:
      'In Italian nearly every word ends in a vowel, and that vowel carries gender and number. **Ragazzo** is a boy; **ragazzi**, several; **ragazza**, a girl. You do not memorise rules — you listen to the ending. So: *casa* is one house; what is "houses"?',
    question: 'How do you say "the girls" in Italian?',
    options: ['Le ragazze', 'Le ragazzi', 'La ragazze'],
    correct: 0,
    correction:
      'The article and the ending change together: *la ragazza* → *le ragazze*. The -i is the masculine plural (*i ragazzi*). Listen to the pair, not the word alone.',
    concepts: [
      { name: 'Final vowels', before: 58, after: 64 },
      { name: 'Article–noun agreement', before: 40, after: 28 },
      { name: 'Present tense', before: 15, after: 15 },
    ],
    card: { front: 'la ragazza → (plural)', back: 'le ragazze' },
  },
  es: {
    label: 'italiano',
    sample:
      'En italiano casi toda palabra termina en vocal, y esa vocal lleva el género y el número. **Ragazzo** es un chico; **ragazzi**, varios; **ragazza**, una chica. No memorizas reglas — escuchas el final. Entonces: *casa* es una; ¿cómo es "casas"?',
    question: '¿Cómo se dice "las chicas" en italiano?',
    options: ['Le ragazze', 'Le ragazzi', 'La ragazze'],
    correct: 0,
    correction:
      'El artículo y la terminación cambian juntos: *la ragazza* → *le ragazze*. La -i es el plural masculino (*i ragazzi*). Escucha el par, no la palabra suelta.',
    concepts: [
      { name: 'Vocales finales', before: 58, after: 64 },
      { name: 'Concordancia artículo–sustantivo', before: 40, after: 28 },
      { name: 'Presente de indicativo', before: 15, after: 15 },
    ],
    card: { front: 'la ragazza → (plural)', back: 'le ragazze' },
  },
};

const JAVASCRIPT: Bank = {
  pt: {
    label: 'JavaScript',
    sample:
      'Em JavaScript, quase tudo que parece mágica é uma função sendo passada como valor. Você entrega uma função para outra e diz "chame isso quando terminar". É o que `addEventListener("click", fazAlgo)` faz: **callback**. Se `fazAlgo` roda depois, onde a variável que ela usa precisa estar viva?',
    question: 'O que `[1, 2, 3].map(n => n * 2)` devolve?',
    options: ['[2, 4, 6]', '6', 'undefined'],
    correct: 0,
    correction:
      '`map` chama a função para cada item e devolve um **novo array** com os resultados. Se você esperava um número, estava pensando em `reduce`; se esperava nada, em `forEach`.',
    concepts: [
      { name: 'Funções como valores', before: 55, after: 60 },
      { name: 'map / filter / reduce', before: 44, after: 30 },
      { name: 'Promises', before: 18, after: 18 },
    ],
    card: { front: '`map` devolve…', back: 'um novo array, mesmo tamanho, itens transformados' },
  },
  en: {
    label: 'JavaScript',
    sample:
      'In JavaScript almost everything that looks like magic is a function being passed around as a value. You hand one function to another and say "call this when you are done". That is what `addEventListener("click", doThing)` does: a **callback**. If `doThing` runs later, where does the variable it uses have to still be alive?',
    question: 'What does `[1, 2, 3].map(n => n * 2)` return?',
    options: ['[2, 4, 6]', '6', 'undefined'],
    correct: 0,
    correction:
      '`map` calls the function for every item and returns a **new array** of the results. If you expected a number you were thinking of `reduce`; if nothing, `forEach`.',
    concepts: [
      { name: 'Functions as values', before: 55, after: 60 },
      { name: 'map / filter / reduce', before: 44, after: 30 },
      { name: 'Promises', before: 18, after: 18 },
    ],
    card: { front: '`map` returns…', back: 'a new array, same length, items transformed' },
  },
  es: {
    label: 'JavaScript',
    sample:
      'En JavaScript casi todo lo que parece magia es una función pasada como valor. Le entregas una función a otra y dices "llama a esto cuando termines". Eso hace `addEventListener("click", hazAlgo)`: un **callback**. Si `hazAlgo` corre después, ¿dónde tiene que seguir viva la variable que usa?',
    question: '¿Qué devuelve `[1, 2, 3].map(n => n * 2)`?',
    options: ['[2, 4, 6]', '6', 'undefined'],
    correct: 0,
    correction:
      '`map` llama a la función por cada elemento y devuelve un **array nuevo** con los resultados. Si esperabas un número pensabas en `reduce`; si nada, en `forEach`.',
    concepts: [
      { name: 'Funciones como valores', before: 55, after: 60 },
      { name: 'map / filter / reduce', before: 44, after: 30 },
      { name: 'Promises', before: 18, after: 18 },
    ],
    card: { front: '`map` devuelve…', back: 'un array nuevo, mismo largo, elementos transformados' },
  },
};

const GENERIC: Record<Locale, (subject: string) => SubjectBank> = {
  pt: (s) => ({
    label: s,
    sample: `Quase tudo em ${s} depende de uma ideia central, e a melhor forma de começar é por um caso concreto que você já conhece — antes de qualquer termo. É assim que a aula abre: **um exemplo, depois o nome**. O que em ${s} você acha que é a peça que sustenta o resto?`,
    question: `Por onde uma aula de ${s} deveria começar?`,
    options: ['Pela lista de termos', 'Por um exemplo concreto', 'Pela história do campo'],
    correct: 1,
    correction:
      'Um termo sem imagem por trás não gruda. O exemplo cria o lugar onde o termo vai morar — por isso ele vem antes.',
    concepts: [
      { name: `Ideia central de ${s}`, before: 50, after: 56 },
      { name: 'Primeiro exemplo', before: 42, after: 30 },
      { name: 'Vocabulário', before: 12, after: 12 },
    ],
    card: { front: `A ideia que sustenta ${s} é…`, back: 'o que a primeira aula ensinou, no seu exemplo' },
  }),
  en: (s) => ({
    label: s,
    sample: `Almost everything in ${s} rests on one central idea, and the best way in is a concrete case you already know — before any term. That is how the lesson opens: **an example, then the name**. What in ${s} do you think is the piece holding the rest up?`,
    question: `Where should a lesson on ${s} begin?`,
    options: ['With the list of terms', 'With a concrete example', 'With the history of the field'],
    correct: 1,
    correction:
      'A term with no picture behind it does not stick. The example builds the place the term will live in — which is why it comes first.',
    concepts: [
      { name: `Central idea of ${s}`, before: 50, after: 56 },
      { name: 'First example', before: 42, after: 30 },
      { name: 'Vocabulary', before: 12, after: 12 },
    ],
    card: { front: `The idea holding ${s} up is…`, back: 'what the first lesson taught, in your example' },
  }),
  es: (s) => ({
    label: s,
    sample: `Casi todo en ${s} descansa en una idea central, y la mejor entrada es un caso concreto que ya conoces — antes de cualquier término. Así abre la lección: **un ejemplo, luego el nombre**. ¿Qué en ${s} crees que es la pieza que sostiene el resto?`,
    question: `¿Por dónde debería empezar una lección de ${s}?`,
    options: ['Por la lista de términos', 'Por un ejemplo concreto', 'Por la historia del campo'],
    correct: 1,
    correction:
      'Un término sin imagen detrás no se queda. El ejemplo construye el lugar donde vivirá el término — por eso va primero.',
    concepts: [
      { name: `Idea central de ${s}`, before: 50, after: 56 },
      { name: 'Primer ejemplo', before: 42, after: 30 },
      { name: 'Vocabulario', before: 12, after: 12 },
    ],
    card: { front: `La idea que sostiene ${s} es…`, back: 'lo que enseñó la primera lección, en tu ejemplo' },
  }),
};

export function bankFor(subject: string, locale: Locale): SubjectBank {
  const s = subject.toLowerCase();
  if (/freud|psican|psychoan|psicoan|psicolog|psycholog/.test(s)) return FREUD[locale];
  if (/italian|italiano/.test(s)) return ITALIAN[locale];
  if (/javascript|\bjs\b|typescript/.test(s)) return JAVASCRIPT[locale];
  return GENERIC[locale](subject.trim());
}
