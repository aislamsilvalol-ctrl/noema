/**
 * The English copy, and the shape every translation must fill.
 *
 * `Dict` is derived from this object, so `pt.ts` and `es.ts` fail to compile if
 * they miss a key. Parameterised strings are functions — each language handles
 * its own plurals and word order instead of the code concatenating fragments
 * that only work in English.
 *
 * Server-generated sentences (plan rationales, calibration summaries, import
 * reports, API error details) are not here: they arrive from the API in English
 * until the backend learns Accept-Language, and pretending otherwise by
 * translating around them would produce half-translated screens.
 */

export const en = {
  common: {
    loading: 'Loading…',
    cancel: 'Cancel',
    create: 'Create',
    creating: 'Creating…',
    delete: 'Delete',
    stop: 'Stop',
    skip: 'Skip',
    send: 'Send',
    save: 'Save',
    finish: 'Finish →',
    next: 'Next →',
    nextQuestion: 'Next question →',
    pickAnother: 'Pick another',
    backToNotebook: 'Back to notebook',
    seeMastery: 'See mastery',
    enterToSend: 'Enter to send',
    somethingWrong: 'Something went wrong.',
    language: 'Language',
  },

  landing: {
    signIn: 'Sign in',
    title1: 'Learn anything.',
    title2: 'Actually remember it.',
    lede: 'NOEMA turns your notes, documents and questions into an adaptive learning system built around how you learn — what you have mastered, what you are forgetting, and what you only think you understand.',
    start: 'Start learning',
    viewGithub: 'View on GitHub',
    pillars: [
      {
        title: 'It models concepts, not cards',
        body: 'A flashcard app knows you failed card 4,182. NOEMA knows you are failing backpropagation because your chain rule mastery is 38%, and it sends you there first.',
      },
      {
        title: 'It catches confident errors',
        body: 'Answer wrong while certain you are right and you have found a misconception — the one failure spaced repetition never catches, because you would never flag it yourself.',
      },
      {
        title: 'It only answers from your materials',
        body: 'Retrieval with enforced citations: source, page, excerpt. When the answer is not in your documents, it says so instead of inventing one.',
      },
      {
        title: 'It can run entirely on your machine',
        body: 'Ollama and local embeddings. Documents, conversations and progress never leave your laptop. No account, no upload, no telemetry.',
      },
    ],
    principle1: 'Every product decision answers one question: ',
    principleEm: 'does this help someone actually learn and remember?',
    principle2: ' If the honest answer is no, it does not ship — however good the demo looks.',
    license: 'AGPL-3.0 · Open source',
    tagline: 'Learn anything. Remember everything.',
  },

  login: {
    welcomeBack: 'Welcome back.',
    startLearning: 'Start learning.',
    signInLede: 'Sign in to pick up where you left off.',
    registerLede: 'Your material stays yours. Export or delete it at any time.',
    name: 'Name',
    email: 'Email',
    password: 'Password',
    passwordHint: 'At least 12 characters. Length beats symbols.',
    signIn: 'Sign in',
    createAccount: 'Create account',
    working: 'Working…',
    noAccount: 'No account yet? Create one',
    haveAccount: 'Already have an account? Sign in',
    signupsClosed:
      'This instance is not open for new accounts. Ask whoever runs it for one, or run your own — NOEMA is open source.',
  },

  nav: {
    today: 'Today',
    library: 'Library',
    goals: 'Goals',
    review: 'Review',
    explain: 'Explain',
    socratic: 'Socratic',
    mistakes: 'Mistakes',
    graph: 'Graph',
    progress: 'Progress',
    settings: 'Settings',
    more: 'More',
    commandPalette: 'Command palette',
    signOut: 'Sign out',
  },

  palette: {
    searchPlaceholder: 'Search commands…',
    noMatch: 'No matching command.',
    ariaLabel: 'Command palette',
    todaySession: "Today's session",
    goLibrary: 'Go to library',
    settingsKeys: 'AI providers and keys',
    reviewDue: 'Review due cards',
    quizMe: 'Quiz me on a notebook',
    quizHint: 'pick one',
    startSession: 'Start a study session',
    explainBack: 'Explain something back',
    goalsByWhen: 'What do I need by when?',
    socraticQuestion: 'Question me until I get it',
    showMap: 'Show me the map',
    whatDoIKnow: 'What do I actually know?',
    reviewMistakes: 'Review my mistakes',
  },

  today: {
    title: 'Today',
    iHave: 'I have',
    planning: 'Planning…',
    couldNotPlan: 'Could not build a plan.',
    emptyTitle: 'Nothing to do right now.',
    emptyBody:
      'Nothing is due and nothing is weak enough to drill. Studying anyway would not help you remember longer — add material, or come back when something is due.',
    startSession: 'Start session',
    aboutMinutes: (n: number) => `about ${n} minutes`,
    lessThanMinute: '<1',
    min: 'min',
    blocks: {
      warmup: 'Warm up',
      repair: 'Repair',
      practice: 'Practice',
      cooldown: 'Wind down',
    } as Record<string, string>,
    kinds: {
      card_review: 'review',
      card_learn: 'new card',
      question: 'question',
      misconception_drill: 'misconception',
      prereq_repair: 'prerequisite',
      read: 'reading',
    } as Record<string, string>,
    countOf: (n: number, label: string) => `${n} ${label}${n === 1 ? '' : 's'}`,
  },

  library: {
    title: 'Library',
    notebookTitle: 'Notebook title',
    notebookPlaceholder: 'Cardiovascular system',
    newNotebook: 'New notebook',
    cardsDue: (n: number) => `${n} ${n === 1 ? 'card' : 'cards'} due`,
    startReviewing: 'Start reviewing →',
    couldNotLoad: 'Could not load your library.',
    couldNotCreate: 'Could not create the notebook.',
    emptyTitle: 'Nothing here yet.',
    emptyBody:
      'A notebook is one subject you are working on — a course, a paper, a chapter. Put material in it and NOEMA starts building a picture of what you know.',
    unfiled: 'Not filed under a subject',
    defaultSubject: 'General',
  },

  notebook: {
    fallbackTitle: 'Notebook',
    exam: 'Exam',
    quiz: 'Quiz',
    cards: 'Cards',
    newNote: 'New note',
    noteTitle: 'Note title',
    notePlaceholder: 'Cardiac cycle',
    saved: 'Saved',
    saving: 'Saving…',
    couldNotOpen: 'Could not open this notebook.',
    couldNotSave: 'Could not save. Your text is still here — check your connection.',
    editorPlaceholder: "Write what you're trying to understand. Type / for blocks.",
    actionExplain: 'Explain',
    actionSimplify: 'Simplify',
    actionExpand: 'Expand',
    actionAsk: 'Ask NOEMA',
    actionFlashcard: 'Flashcard',
    actionQuestion: 'Question',
    dismiss: 'Dismiss',
    nothingWritten: 'Nothing here has been written into your note.',
    noNotes:
      'No notes yet. Notes exist to become questions — write what you are trying to understand, not what you already know.',
  },

  sources: {
    documents: 'Documents',
    dropHere: 'Drop a PDF, DOCX, Markdown, text or CSV file here',
    uploading: 'Uploading…',
    untitled: 'Untitled',
    stages: {
      pending: 'queued',
      parsing: 'reading the file',
      chunking: 'splitting it up',
      embedding: 'indexing',
      extracting: 'finding concepts',
      ready: 'ready',
      failed: 'failed',
    } as Record<string, string>,
    couldNotList: 'Could not list documents.',
    notAccepted: 'That file was not accepted.',
  },

  anki: {
    fromAnki: 'From Anki',
    lede: 'Import an .apkg export. Your intervals come with it, so cards you already know are not asked again from scratch.',
    chooseDeck: 'Choose a deck',
    reading: 'Reading the deck…',
    notImported: 'The deck could not be imported.',
    approximation:
      'The imported intervals are a starting position translated from Anki’s, not an exact conversion. Your next few reviews correct them.',
    skippedRow: (n: number, reason: string) => `${n} skipped — ${reason}.`,
  },

  cards: {
    title: 'Cards',
    draft: 'Draft from material',
    drafting: 'Drafting…',
    generationFailed: 'Generation failed.',
    nothingToDraft:
      'Nothing new to draft. Add material, or the model found no card worth making.',
    waiting: 'Waiting for you',
    waitingLede:
      'Drafted cards do not enter your rotation until you have read them. Spaced repetition is very good at making a wrong card permanent — edit anything that is off before approving it.',
    nothingWaiting: 'Nothing waiting.',
    approve: 'Approve',
    discard: 'Discard',
    noConcept: 'no concept matched',
    couldNotApprove: 'Could not approve that card.',
    couldNotLoad: 'Could not load cards.',
    inRotation: 'In rotation',
    noCards: 'No cards yet.',
    newCard: 'new',
    reviews: (n: number) => `${n} reviews`,
    question: 'Question',
    answer: 'Answer',
    writeOwn: 'Write your own',
    frontPlaceholder: 'Question or prompt',
    backPlaceholder: 'Answer',
    attachImage: 'Attach an image (optional)',
    addCard: 'Add card',
    adding: 'Adding…',
    couldNotCreate: 'Could not create that card.',
    alsoReverse: 'Also make the reverse card (answer → question, its own schedule)',
    modeBasic: 'Basic',
    modeCloze: 'Cloze',
    clozePlaceholder: 'Text with {{c1::a deletion}} — wrap what should be hidden.',
    clozeHint: 'One card per numbered deletion. {{c1::x}} twice hides both together.',
  },

  review: {
    loadFailed: 'Could not load your cards.',
    saveFailed: 'A review could not be saved. It will need answering again.',
    cardImageAlt: 'Card image',
    queued: (n: number) =>
      `${n} ${n === 1 ? 'review' : 'reviews'} saved offline — will sync when you're back online.`,
    sessionComplete: 'Session complete.',
    nothingDue: 'Nothing due.',
    reviewedCount: (n: number) =>
      `${n} ${n === 1 ? 'card' : 'cards'} reviewed. The next ones are scheduled for when you are about to forget them.`,
    nothingDueBody:
      'No cards are due right now. Come back when something is — reviewing early does not help you remember longer.',
    position: (done: number, total: number) => `${done} of ${total}`,
    newTag: 'new',
    showAnswer: 'Show answer',
    space: 'space',
    howConfident: 'How confident were you?',
    rateHonestly: 'Rate honestly — the schedule is only as good as the grade you give it.',
    tryFirst: 'Try to recall it before revealing. The effort is the point.',
    ratings: {
      again: { label: 'Again', meaning: 'could not recall' },
      hard: { label: 'Hard', meaning: 'with effort' },
      good: { label: 'Good', meaning: 'recalled' },
      easy: { label: 'Easy', meaning: 'instant' },
    },
    confidence: ['Guess', 'Unsure', 'Somewhat', 'Confident', 'Certain'],
  },

  question: {
    howConfident: 'How confident are you?',
    correct: 'Correct',
    notQuite: 'Not quite',
    notRecorded: 'That answer was not recorded.',
    confidence: ['Guess', 'Unsure', 'Somewhat', 'Confident', 'Certain'],
    trueLabel: 'True',
    falseLabel: 'False',
    missingWord: 'The missing word',
    ownWords: 'Answer in your own words.',
    moveUp: (item: string) => `Move ${item} up`,
    moveDown: (item: string) => `Move ${item} down`,
    answerCta: 'Answer',
    gradedByYou: ' · graded by you, no model configured',
    whatWasMissing: 'What was missing',
    positionOf: (n: number, total: number, difficulty: string) =>
      `${n} of ${total} · ${difficulty}`,
  },

  quiz: {
    title: 'Quiz',
    couldNotLoad: 'Could not load questions.',
    couldNotGenerate: 'Questions could not be generated from this notebook.',
    done: 'Done.',
    noneMissed: (n: number) =>
      `${n} answered, none missed. Those concepts are scheduled further out now.`,
    someMissed: (n: number, wrong: number) =>
      `${n} answered, ${wrong} missed. The ones you got wrong are in your mistakes, with what you said and why it was marked down.`,
    reviewMisses: 'Review the misses',
    newQuestions: 'New questions',
    writing: 'Writing questions…',
    generate: 'Generate questions',
    emptyTitle: 'No questions yet.',
    emptyBody:
      'Questions are written from what you put in this notebook, so upload a document or write a note first. Generated questions are drafts — they can be wrong, and answering them still teaches you nothing if the source was thin.',
  },

  exam: {
    title: 'Exam',
    couldNotStart: 'The exam could not be started.',
    notAccepted: 'The paper was not accepted.',
    sitLede: 'Sit an exam.',
    sitBody:
      'Questions are drawn at random from this notebook, not chosen from what you are worst at — an exam that quietly asks you what you already know you do not know is a drill, and its number means nothing next to the last one. Nothing is marked until you hand in.',
    tenQuestions: '10 questions · 15 min',
    twentyQuestions: '20 questions · 30 min',
    overtime: 'Handed in after time. It still counted.',
    whereItWent: 'Where it went',
    aftermath:
      'The concepts at the top are where the marks went. Everything you got wrong is in your mistakes, and the mastery scores have already moved.',
    reviewMisses: 'Review the misses',
    seeMastery: 'See mastery',
    answered: (done: number, total: number) =>
      `${done} of ${total} answered. Nothing is marked until you hand in.`,
    handIn: 'Hand in',
    marking: 'Marking…',
    unansweredWrong: 'Unanswered questions count as wrong.',
  },

  mistakes: {
    title: 'Mistakes',
    practising: 'Practising misses',
    practiseThese: 'Practise these',
    couldNotLoad: 'Could not load your mistakes.',
    noLongerAvailable: 'Those questions are no longer available.',
    couldNotStartDrill: 'Could not start the drill.',
    couldNotWriteDrills: 'Could not write the drills.',
    slipNotBelief:
      'No correction questions could be written for this one — it reads more like a slip than a belief.',
    youBelieve: (belief: string) => `You appear to believe: ${belief}`,
    emptyTitle: 'Nothing here.',
    emptyBody:
      'Answer some questions and the ones you get wrong land here — with what you said, so you can see the shape of the error rather than just that there was one.',
    confidentlyWrong: 'Confidently wrong',
    confidentlyWrongLede:
      'You were sure and it was wrong. These come first because nothing else will prompt you to look at them again.',
    everythingElse: 'Everything else',
    tryAgain: 'Try it again →',
    breakBelief: 'Break the belief →',
  },

  progress: {
    title: 'Progress',
    couldNotLoad: 'Could not load your progress.',
    whatYouKnow: 'What you know',
    emptyMastery:
      'Nothing scored yet. Mastery is computed per concept from answers and reviews, so it appears once a document has been read and questions have been answered — not from having uploaded something.',
    provisional: 'provisional — too little evidence to trust yet',
    bands: { solid: 'Solid', holding: 'Holding', shaky: 'Shaky', weak: 'Weak' },
    howOftenRight: 'How often you get it right',
    recallNow: 'How likely you are to recall it now',
    fromPrereqs: 'Expected from its prerequisites',
    evidence: 'Evidence behind the score',
    answers: 'answers',
    whatIsComing: 'What is coming',
    nothingScheduled: 'Nothing scheduled in the next two weeks.',
    reviewsOver: (total: number, days: number, busiest: number) =>
      `${total} reviews over the next ${days} days, busiest day ${busiest}. Spikes are worth knowing about before they arrive.`,
    hasItBeenRight: 'Has it been right?',
    predicted: 'It predicted you would recall',
    actual: 'You actually recalled',
    reviewsScored: 'Reviews scored',
    notEnoughHistory:
      'Not enough history to claim anything yet. The numbers appear once there are enough scored reviews to mean something.',
    fitTitle: 'Fit the schedule to you',
    fitLede:
      'The memory model ships with parameters fitted on a large public dataset. They are a good starting point and they are not you. This searches your earlier reviews for better ones and checks them against your later ones — adopting them only if they win on reviews the search never saw.',
    fitCta: 'Fit to my history',
    fitting: 'Fitting…',
    fitFailed: 'The fit could not run.',
  },

  goals: {
    title: 'Goals',
    newGoal: 'New goal',
    goalLabel: 'Goal',
    goalPlaceholder: 'Pass the cardiovascular exam',
    notebook: 'Notebook',
    by: 'By',
    minutesADay: 'Minutes a day',
    setGoal: 'Set the goal',
    workingOut: 'Working it out…',
    toldStraightAway: 'You will be told straight away whether it fits.',
    couldNotLoad: 'Could not load your goals.',
    notCreated: 'The goal was not created.',
    emptyTitle: 'Nothing due.',
    emptyBody:
      'A goal is a notebook, a date, and how long you can give it each day. NOEMA works out the order — prerequisites before what rests on them — and tells you if the date does not fit before you find out the hard way.',
    daysLeft: (n: number) => `${n}d`,
    projection: (projected: number, target: number) =>
      `At this pace you would arrive around ${projected}, against a target of ${target}.`,
  },

  settings: {
    title: 'Settings',
    localModeNote1: 'This deployment runs in ',
    localMode: 'local mode',
    localModeNote2:
      '. Models run on this machine, and the containers holding your material have no route to the internet — so hosted providers are not offered here rather than failing when you click them.',
    providers: 'AI providers',
    providersLocalLede: (provider: string) =>
      `Answering and embedding run locally through ${provider}. Nothing is sent anywhere.`,
    providersLede:
      'Keys are encrypted before they are stored and are never returned by the API — only the last four characters. Delete one and it is gone.',
    default: 'default',
    configured: 'configured',
    noKey: 'no key',
    addKey: 'Add a key',
    provider: 'Provider',
    apiKey: 'API key',
    verifying: 'Verifying…',
    couldNotSaveKey: 'Could not save that key.',
    languageLede:
      'Detected from your browser unless you choose one. The choice is remembered on this device.',
    yourData: 'Your data',
    yourDataLede:
      'The export is a zip: your notes as Markdown, your uploads exactly as you gave them to us, and everything derived — concepts, cards, mastery — as JSON. None of it needs NOEMA to open.',
    exportEverything: 'Export everything',
    preparing: 'Preparing…',
    exportFailed: 'The export failed.',
    deleteAccount: 'Delete this account',
    deleteLede:
      'You are signed out immediately and the account stops working. Everything — notes, uploads, cards, review history — is permanently deleted after 30 days. Export first; after that there is nothing to recover.',
    typeEmail: 'Type your email to confirm',
    deleteMyAccount: 'Delete my account',
    notDeleted: 'The account was not deleted.',
  },

  explain: {
    title: 'Explain it',
    couldNotLoadConcepts: 'Could not load your concepts.',
    notEvaluated: 'The explanation could not be evaluated.',
    lede: 'Explain a concept as if the reader knows nothing about it. You will be told what the explanation assumes, skips or gets away with — judged against your own material, not against what a model happens to know.',
    noConcepts:
      'No concepts yet. They are extracted from documents you upload, so this fills up once a notebook has material in it.',
    placeholder:
      'Explain it in your own words. Write as if to someone who has never heard of it.',
    check: 'Check my explanation',
    readingIt: 'Reading it…',
    writeMore: 'Write a little more first.',
    nothingShown: 'Nothing is shown from your notes until you have written.',
    understood: (pct: number) =>
      `It understood ${pct}% of what your material says about this.`,
    nothingMissing:
      'Nothing missing against your material. That is a real result, not a formality — the harder test is explaining it again in a week.',
    counted: (concept: string) =>
      `This counted towards ${concept} — explaining unaided is weighed as a hard item.`,
    findings: {
      gaps: 'Asserted but not justified',
      oversimplifications: 'True only in a special case',
      assumed: 'Assumed without naming',
      contradictions: 'Cannot both be true',
    },
  },

  socratic: {
    title: 'Socratic',
    lede: 'You will be asked questions, one at a time, and never given the answer. It ends when you have said the thing yourself — being told it and agreeing does not count.',
    noConcepts: 'No concepts yet. They come from documents you upload.',
    couldNotLoad: 'Could not load your concepts.',
    couldNotContinue: 'The dialogue could not continue.',
    thinking: 'Thinking…',
    you: 'You',
    replyPlaceholder: 'Answer in your own words.',
    answer: 'Answer',
    gotThere: 'You got there yourself, which is the only way this ends well.',
    exhausted: 'That is as far as this went today. What you showed still counted.',
    recorded: 'Recorded.',
  },

  graph: {
    title: 'Graph',
    depth: 'Depth',
    couldNotLoadConcepts: 'Could not load your concepts.',
    couldNotLoadGraph: 'Could not load the graph.',
    emptyTitle: 'No concepts yet.',
    emptyBody:
      'Concepts and the edges between them are extracted from documents you upload. Once a notebook has material in it, this fills in.',
    startSomewhere: 'Start somewhere',
    allConcepts: 'All concepts',
    graphLabel: (nodes: number, edges: number) =>
      `Concept graph: ${nodes} concepts, ${edges} connections`,
    nodeUnscored: (name: string) => `${name}, not scored yet`,
    nodeScored: (name: string, score: number) => `${name}, mastery ${score}`,
  },

  tutor: {
    title: 'Tutor',
    emptyLede:
      'Ask about this notebook. Once documents are indexed, answers cite the page they came from — and say so when the answer is not in your material.',
    you: 'You',
    placeholder: 'Ask NOEMA…',
    unavailable: 'The tutor is unavailable.',
    modes: {
      explain: { label: 'Explain', blurb: 'Direct answers, worked examples.' },
      socratic: { label: 'Socratic', blurb: 'Questions only. You reach the answer.' },
      examiner: { label: 'Examiner', blurb: 'Tests you. No hints.' },
      study_partner: { label: 'Partner', blurb: 'Thinks alongside you.' },
      feynman: { label: 'Feynman', blurb: 'You explain. It finds the gaps.' },
    },
  },
};

export type Dict = typeof en;
