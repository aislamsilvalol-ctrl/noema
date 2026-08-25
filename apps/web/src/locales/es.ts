/**
 * Español (neutro, con oído latinoamericano).
 *
 * Traducido como escritura, no como diccionario: la voz del producto — directa,
 * sin jerga de marketing, honesta sobre sus límites — importa más que la
 * correspondencia palabra por palabra. El tipo `Dict` garantiza que no falte
 * ninguna clave.
 */

import type { Dict } from './en';

export const es: Dict = {
  common: {
    loading: 'Cargando…',
    cancel: 'Cancelar',
    create: 'Crear',
    creating: 'Creando…',
    delete: 'Eliminar',
    stop: 'Detener',
    skip: 'Omitir',
    send: 'Enviar',
    save: 'Guardar',
    finish: 'Terminar →',
    next: 'Siguiente →',
    nextQuestion: 'Siguiente pregunta →',
    pickAnother: 'Elegir otro',
    backToNotebook: 'Volver al cuaderno',
    seeMastery: 'Ver dominio',
    enterToSend: 'Enter envía',
    somethingWrong: 'Algo salió mal.',
    language: 'Idioma',
  },

  landing: {
    signIn: 'Iniciar sesión',
    title1: 'Aprende lo que sea.',
    title2: 'Y recuérdalo de verdad.',
    lede: 'NOEMA convierte tus apuntes, documentos y preguntas en un sistema de aprendizaje adaptativo construido alrededor de cómo aprendes: lo que dominas, lo que estás olvidando y lo que solo crees entender.',
    start: 'Empezar a aprender',
    viewGithub: 'Ver en GitHub',
    pillars: [
      {
        title: 'Modela conceptos, no tarjetas',
        body: 'Una app de flashcards sabe que fallaste la tarjeta 4.182. NOEMA sabe que estás fallando en backpropagation porque tu dominio de la regla de la cadena está en 38%, y te manda ahí primero.',
      },
      {
        title: 'Atrapa los errores confiados',
        body: 'Responde mal estando seguro de tener razón y habrás encontrado un malentendido: el único fallo que la repetición espaciada nunca atrapa sola, porque tú jamás lo señalarías.',
      },
      {
        title: 'Solo responde desde tus materiales',
        body: 'Búsqueda con citas obligatorias: fuente, página, fragmento. Cuando la respuesta no está en tus documentos, lo dice en vez de inventarse una.',
      },
      {
        title: 'Puede correr entero en tu máquina',
        body: 'Ollama y embeddings locales. Documentos, conversaciones y progreso nunca salen de tu computadora. Sin cuenta, sin subir nada, sin telemetría.',
      },
    ],
    principle1: 'Cada decisión de producto responde a una pregunta: ',
    principleEm: '¿esto ayuda a alguien a aprender y recordar de verdad?',
    principle2: ' Si la respuesta honesta es no, no se lanza — por bien que se vea en la demo.',
    license: 'AGPL-3.0 · Código abierto',
    tagline: 'Aprende lo que sea. Recuérdalo todo.',
  },

  login: {
    welcomeBack: 'Bienvenido de vuelta.',
    startLearning: 'Empieza a aprender.',
    signInLede: 'Inicia sesión para seguir donde quedaste.',
    registerLede: 'Tu material sigue siendo tuyo. Expórtalo o bórralo cuando quieras.',
    name: 'Nombre',
    email: 'Correo',
    password: 'Contraseña',
    passwordHint: 'Al menos 12 caracteres. El largo vale más que los símbolos.',
    signIn: 'Iniciar sesión',
    createAccount: 'Crear cuenta',
    working: 'Entrando…',
    noAccount: '¿Sin cuenta todavía? Crea una',
    haveAccount: '¿Ya tienes cuenta? Inicia sesión',
    signupsClosed:
      'Esta instancia no acepta cuentas nuevas. Pídele una a quien la administra, o monta la tuya — NOEMA es código abierto.',
  },

  nav: {
    today: 'Hoy',
    library: 'Biblioteca',
    goals: 'Metas',
    review: 'Repasar',
    explain: 'Explicar',
    socratic: 'Socrático',
    mistakes: 'Errores',
    graph: 'Grafo',
    progress: 'Progreso',
    settings: 'Ajustes',
    more: 'Más',
    commandPalette: 'Paleta de comandos',
    signOut: 'Cerrar sesión',
  },

  palette: {
    searchPlaceholder: 'Buscar comandos…',
    noMatch: 'Ningún comando coincide.',
    ariaLabel: 'Paleta de comandos',
    todaySession: 'La sesión de hoy',
    goLibrary: 'Ir a la biblioteca',
    settingsKeys: 'Proveedores de IA y claves',
    reviewDue: 'Repasar tarjetas pendientes',
    quizMe: 'Quiz sobre un cuaderno',
    quizHint: 'elige uno',
    startSession: 'Empezar una sesión de estudio',
    explainBack: 'Explicar algo de vuelta',
    goalsByWhen: '¿Qué necesito y para cuándo?',
    socraticQuestion: 'Cuestióname hasta que lo entienda',
    showMap: 'Muéstrame el mapa',
    whatDoIKnow: '¿Qué sé de verdad?',
    reviewMistakes: 'Repasar mis errores',
  },

  today: {
    title: 'Hoy',
    iHave: 'Tengo',
    planning: 'Planificando…',
    couldNotPlan: 'No se pudo armar un plan.',
    emptyTitle: 'Nada que hacer ahora.',
    emptyBody:
      'Nada está por vencer y nada está tan débil como para entrenarlo. Estudiar igual no te haría recordar más tiempo — agrega material, o vuelve cuando algo esté por vencer.',
    startSession: 'Empezar sesión',
    aboutMinutes: (n: number) => `unos ${n} minutos`,
    lessThanMinute: '<1',
    min: 'min',
    blocks: {
      warmup: 'Calentamiento',
      repair: 'Reparación',
      practice: 'Práctica',
      cooldown: 'Cierre',
    } as Record<string, string>,
    kinds: {
      card_review: 'repaso',
      card_learn: 'tarjeta nueva',
      question: 'pregunta',
      misconception_drill: 'malentendido',
      prereq_repair: 'prerrequisito',
      read: 'lectura',
    } as Record<string, string>,
    countOf: (n: number, label: string) => {
      if (n === 1) return `1 ${label}`;
      const plural = label === 'tarjeta nueva' ? 'tarjetas nuevas' : `${label}s`;
      return `${n} ${plural}`;
    },
  },

  library: {
    title: 'Biblioteca',
    notebookTitle: 'Título del cuaderno',
    notebookPlaceholder: 'Sistema cardiovascular',
    newNotebook: 'Nuevo cuaderno',
    cardsDue: (n: number) =>
      `${n} ${n === 1 ? 'tarjeta pendiente' : 'tarjetas pendientes'}`,
    startReviewing: 'Empezar a repasar →',
    couldNotLoad: 'No se pudo cargar tu biblioteca.',
    couldNotCreate: 'No se pudo crear el cuaderno.',
    emptyTitle: 'Nada por aquí todavía.',
    emptyBody:
      'Un cuaderno es un tema en el que estás trabajando: un curso, un artículo, un capítulo. Ponle material y NOEMA empieza a armar un retrato de lo que sabes.',
    unfiled: 'Sin materia asignada',
    defaultSubject: 'General',
  },

  notebook: {
    fallbackTitle: 'Cuaderno',
    exam: 'Examen',
    quiz: 'Quiz',
    cards: 'Tarjetas',
    newNote: 'Nueva nota',
    noteTitle: 'Título de la nota',
    notePlaceholder: 'Ciclo cardíaco',
    saved: 'Guardado',
    saving: 'Guardando…',
    couldNotOpen: 'No se pudo abrir este cuaderno.',
    couldNotSave: 'No se pudo guardar. Tu texto sigue aquí — revisa la conexión.',
    editorPlaceholder: 'Escribe lo que intentas entender. Teclea / para bloques.',
    actionExplain: 'Explicar',
    actionSimplify: 'Simplificar',
    actionExpand: 'Ampliar',
    actionAsk: 'Preguntar a NOEMA',
    actionFlashcard: 'Flashcard',
    actionQuestion: 'Pregunta',
    dismiss: 'Descartar',
    nothingWritten: 'Nada de esto se escribió en tu nota.',
    noNotes:
      'Ninguna nota todavía. Las notas existen para volverse preguntas — escribe lo que intentas entender, no lo que ya sabes.',
  },

  sources: {
    documents: 'Documentos',
    dropHere: 'Suelta aquí un PDF, DOCX, Markdown, texto o CSV',
    uploading: 'Subiendo…',
    untitled: 'Sin título',
    stages: {
      pending: 'en cola',
      parsing: 'leyendo el archivo',
      chunking: 'dividiéndolo',
      embedding: 'indexando',
      extracting: 'hallando conceptos',
      ready: 'listo',
      failed: 'falló',
    } as Record<string, string>,
    couldNotList: 'No se pudieron listar los documentos.',
    notAccepted: 'Ese archivo no fue aceptado.',
  },

  anki: {
    fromAnki: 'Desde Anki',
    lede: 'Importa una exportación .apkg. Tus intervalos vienen con ella, así que las tarjetas que ya sabes no vuelven a empezar de cero.',
    chooseDeck: 'Elegir un mazo',
    reading: 'Leyendo el mazo…',
    notImported: 'No se pudo importar el mazo.',
    approximation:
      'Los intervalos importados son un punto de partida traducido de los de Anki, no una conversión exacta. Tus próximos repasos los corrigen.',
    skippedRow: (n: number, reason: string) => `${n} omitidas — ${reason}.`,
  },

  cards: {
    title: 'Tarjetas',
    draft: 'Redactar del material',
    drafting: 'Redactando…',
    generationFailed: 'La generación falló.',
    nothingToDraft:
      'Nada nuevo que redactar. Agrega material, o el modelo no encontró tarjeta que valiera la pena.',
    waiting: 'Esperándote',
    waitingLede:
      'Las tarjetas redactadas no entran a tu rotación hasta que las hayas leído. La repetición espaciada es muy buena volviendo permanente una tarjeta errónea — corrige lo que esté mal antes de aprobar.',
    nothingWaiting: 'Nada en espera.',
    approve: 'Aprobar',
    discard: 'Descartar',
    noConcept: 'sin concepto asociado',
    couldNotApprove: 'No se pudo aprobar esa tarjeta.',
    couldNotLoad: 'No se pudieron cargar las tarjetas.',
    inRotation: 'En rotación',
    noCards: 'Ninguna tarjeta todavía.',
    newCard: 'nueva',
    reviews: (n: number) => `${n} ${n === 1 ? 'repaso' : 'repasos'}`,
    question: 'Pregunta',
    answer: 'Respuesta',
  },

  review: {
    loadFailed: 'No se pudieron cargar tus tarjetas.',
    saveFailed: 'Un repaso no se pudo guardar. Habrá que responderlo de nuevo.',
    cardImageAlt: 'Imagen de la tarjeta',
    queued: (n: number) =>
      `${n} ${n === 1 ? 'repaso guardado' : 'repasos guardados'} sin conexión — se sincronizarán cuando vuelvas a estar en línea.`,
    sessionComplete: 'Sesión completa.',
    nothingDue: 'Nada pendiente.',
    reviewedCount: (n: number) =>
      `${n} ${n === 1 ? 'tarjeta repasada' : 'tarjetas repasadas'}. Las próximas están agendadas para cuando estés a punto de olvidarlas.`,
    nothingDueBody:
      'Ninguna tarjeta está pendiente ahora. Vuelve cuando alguna lo esté — repasar antes de tiempo no te hace recordar más.',
    position: (done: number, total: number) => `${done} de ${total}`,
    newTag: 'nueva',
    showAnswer: 'Mostrar respuesta',
    space: 'espacio',
    howConfident: '¿Qué tan seguro estabas?',
    rateHonestly: 'Califica con honestidad — el calendario vale lo que vale la nota que le das.',
    tryFirst: 'Intenta recordarlo antes de revelar. El esfuerzo es el punto.',
    ratings: {
      again: { label: 'Otra vez', meaning: 'no lo recordé' },
      hard: { label: 'Difícil', meaning: 'con esfuerzo' },
      good: { label: 'Bien', meaning: 'lo recordé' },
      easy: { label: 'Fácil', meaning: 'al instante' },
    },
    confidence: ['Adiviné', 'Inseguro', 'Más o menos', 'Confiado', 'Seguro'],
  },

  question: {
    howConfident: '¿Qué tan seguro estás?',
    correct: 'Correcto',
    notQuite: 'No exactamente',
    notRecorded: 'Esa respuesta no quedó registrada.',
    confidence: ['Adiviné', 'Inseguro', 'Más o menos', 'Confiado', 'Seguro'],
    trueLabel: 'Verdadero',
    falseLabel: 'Falso',
    missingWord: 'La palabra que falta',
    ownWords: 'Responde con tus palabras.',
    moveUp: (item: string) => `Subir ${item}`,
    moveDown: (item: string) => `Bajar ${item}`,
    answerCta: 'Responder',
    gradedByYou: ' · calificado por ti, sin modelo configurado',
    whatWasMissing: 'Lo que faltó',
    positionOf: (n: number, total: number, difficulty: string) =>
      `${n} de ${total} · ${difficulty}`,
  },

  quiz: {
    title: 'Quiz',
    couldNotLoad: 'No se pudieron cargar las preguntas.',
    couldNotGenerate: 'No se pudieron generar preguntas de este cuaderno.',
    done: 'Listo.',
    noneMissed: (n: number) =>
      `${n} respondidas, ninguna mal. Esos conceptos quedaron agendados más lejos.`,
    someMissed: (n: number, wrong: number) =>
      `${n} respondidas, ${wrong} mal. Las que fallaste están en tus errores, con lo que dijiste y por qué se descontó.`,
    reviewMisses: 'Repasar los fallos',
    newQuestions: 'Nuevas preguntas',
    writing: 'Escribiendo preguntas…',
    generate: 'Generar preguntas',
    emptyTitle: 'Ninguna pregunta todavía.',
    emptyBody:
      'Las preguntas se escriben a partir de lo que pusiste en este cuaderno — sube un documento o escribe una nota primero. Las preguntas generadas son borradores: pueden estar mal, y responderlas no enseña nada si la fuente era pobre.',
  },

  exam: {
    title: 'Examen',
    couldNotStart: 'No se pudo iniciar el examen.',
    notAccepted: 'El examen no fue aceptado.',
    sitLede: 'Rinde un examen.',
    sitBody:
      'Las preguntas se sortean de este cuaderno, no se eligen por lo que peor llevas — un examen que en silencio te pregunta lo que ya sabes que no sabes es un entrenamiento, y su nota no significa nada junto a la anterior. Nada se corrige hasta que entregas.',
    tenQuestions: '10 preguntas · 15 min',
    twentyQuestions: '20 preguntas · 30 min',
    overtime: 'Entregado fuera de tiempo. Contó igual.',
    whereItWent: 'A dónde se fue',
    aftermath:
      'Los conceptos de arriba son donde se fueron los puntos. Todo lo que fallaste está en tus errores, y los índices de dominio ya se movieron.',
    reviewMisses: 'Repasar los fallos',
    seeMastery: 'Ver dominio',
    answered: (done: number, total: number) =>
      `${done} de ${total} respondidas. Nada se corrige hasta que entregas.`,
    handIn: 'Entregar',
    marking: 'Corrigiendo…',
    unansweredWrong: 'Las preguntas en blanco cuentan como mal.',
  },

  mistakes: {
    title: 'Errores',
    practising: 'Practicando los fallos',
    practiseThese: 'Practicar estos',
    couldNotLoad: 'No se pudieron cargar tus errores.',
    noLongerAvailable: 'Esas preguntas ya no están disponibles.',
    couldNotStartDrill: 'No se pudo iniciar el entrenamiento.',
    couldNotWriteDrills: 'No se pudieron escribir los entrenamientos.',
    slipNotBelief:
      'No se pudieron escribir preguntas de corrección para este — parece más un descuido que una creencia.',
    youBelieve: (belief: string) => `Pareces creer que: ${belief}`,
    emptyTitle: 'Nada por aquí.',
    emptyBody:
      'Responde algunas preguntas y las que falles aterrizan aquí — con lo que dijiste, para que veas la forma del error y no solo que lo hubo.',
    confidentlyWrong: 'Mal con confianza',
    confidentlyWrongLede:
      'Estabas seguro y estaba mal. Estos van primero porque nada más te hará mirarlos de nuevo.',
    everythingElse: 'Todo lo demás',
    tryAgain: 'Intentarlo de nuevo →',
    breakBelief: 'Romper la creencia →',
  },

  progress: {
    title: 'Progreso',
    couldNotLoad: 'No se pudo cargar tu progreso.',
    whatYouKnow: 'Lo que sabes',
    emptyMastery:
      'Nada puntuado todavía. El dominio se calcula por concepto a partir de respuestas y repasos — aparece cuando un documento fue leído y hubo preguntas respondidas, no por haber subido algo.',
    provisional: 'provisional — muy poca evidencia para confiar',
    bands: { solid: 'Sólido', holding: 'Firme', shaky: 'Inestable', weak: 'Débil' },
    howOftenRight: 'Con qué frecuencia aciertas',
    recallNow: 'Probabilidad de recordarlo ahora',
    fromPrereqs: 'Esperado por sus prerrequisitos',
    evidence: 'Evidencia detrás del índice',
    answers: 'respuestas',
    whatIsComing: 'Lo que viene',
    nothingScheduled: 'Nada agendado en las próximas dos semanas.',
    reviewsOver: (total: number, days: number, busiest: number) =>
      `${total} repasos en los próximos ${days} días, pico de ${busiest} en un día. Los picos conviene conocerlos antes de que lleguen.`,
    hasItBeenRight: '¿Ha acertado?',
    predicted: 'Predijo que recordarías',
    actual: 'De hecho recordaste',
    reviewsScored: 'Repasos puntuados',
    notEnoughHistory:
      'Muy poco historial para afirmar nada. Los números aparecen cuando haya suficientes repasos puntuados como para significar algo.',
    fitTitle: 'Ajustar el calendario a ti',
    fitLede:
      'El modelo de memoria trae parámetros ajustados sobre un gran conjunto público de datos. Son un buen punto de partida, y no son tú. Esto busca parámetros mejores en tus repasos antiguos y los verifica contra los recientes — adoptándolos solo si ganan en repasos que la búsqueda nunca vio.',
    fitCta: 'Ajustar a mi historial',
    fitting: 'Ajustando…',
    fitFailed: 'El ajuste no pudo correr.',
  },

  goals: {
    title: 'Metas',
    newGoal: 'Nueva meta',
    goalLabel: 'Meta',
    goalPlaceholder: 'Aprobar el examen de cardiovascular',
    notebook: 'Cuaderno',
    by: 'Para',
    minutesADay: 'Minutos al día',
    setGoal: 'Fijar la meta',
    workingOut: 'Calculando…',
    toldStraightAway: 'Sabrás de inmediato si la fecha alcanza.',
    couldNotLoad: 'No se pudieron cargar tus metas.',
    notCreated: 'La meta no fue creada.',
    emptyTitle: 'Nada con fecha.',
    emptyBody:
      'Una meta es un cuaderno, una fecha y cuánto tiempo al día puedes darle. NOEMA resuelve el orden — prerrequisitos antes de lo que se apoya en ellos — y avisa si la fecha no alcanza antes de que lo descubras por las malas.',
    daysLeft: (n: number) => `${n}d`,
    projection: (projected: number, target: number) =>
      `A este ritmo llegarías alrededor de ${projected}, contra una meta de ${target}.`,
  },

  settings: {
    title: 'Ajustes',
    localModeNote1: 'Esta instancia corre en ',
    localMode: 'modo local',
    localModeNote2:
      '. Los modelos corren en esta máquina, y los contenedores con tu material no tienen ruta a internet — por eso los proveedores alojados ni se ofrecen aquí, en vez de fallar cuando haces clic.',
    providers: 'Proveedores de IA',
    providersLocalLede: (provider: string) =>
      `Respuestas y embeddings corren localmente vía ${provider}. Nada se envía a ningún lado.`,
    providersLede:
      'Las claves se cifran antes de guardarse y la API nunca las devuelve — solo los últimos cuatro caracteres. La borras y desaparece.',
    default: 'predeterminado',
    configured: 'configurado',
    noKey: 'sin clave',
    addKey: 'Agregar una clave',
    provider: 'Proveedor',
    apiKey: 'Clave de API',
    verifying: 'Verificando…',
    couldNotSaveKey: 'No se pudo guardar esa clave.',
    languageLede:
      'Detectado desde tu navegador, salvo que elijas uno. La elección se recuerda en este dispositivo.',
    yourData: 'Tus datos',
    yourDataLede:
      'La exportación es un zip: tus notas en Markdown, tus archivos tal como los subiste, y todo lo derivado — conceptos, tarjetas, dominio — en JSON. Nada de eso necesita NOEMA para abrirse.',
    exportEverything: 'Exportar todo',
    preparing: 'Preparando…',
    exportFailed: 'La exportación falló.',
    deleteAccount: 'Eliminar esta cuenta',
    deleteLede:
      'Quedas desconectado de inmediato y la cuenta deja de funcionar. Todo — notas, archivos, tarjetas, historial de repasos — se borra definitivamente a los 30 días. Exporta primero; después no hay nada que recuperar.',
    typeEmail: 'Escribe tu correo para confirmar',
    deleteMyAccount: 'Eliminar mi cuenta',
    notDeleted: 'La cuenta no fue eliminada.',
  },

  explain: {
    title: 'Explícalo',
    couldNotLoadConcepts: 'No se pudieron cargar tus conceptos.',
    notEvaluated: 'La explicación no pudo evaluarse.',
    lede: 'Explica un concepto como si el lector no supiera nada de él. Se te dirá qué asume, qué salta y qué deja pasar tu explicación — juzgada contra tu propio material, no contra lo que un modelo casualmente sabe.',
    noConcepts:
      'Ningún concepto todavía. Se extraen de los documentos que subes, así que esto se llena cuando un cuaderno tenga material.',
    placeholder:
      'Explícalo con tus palabras. Escribe como para alguien que nunca oyó hablar de esto.',
    check: 'Revisar mi explicación',
    readingIt: 'Leyéndola…',
    writeMore: 'Escribe un poco más primero.',
    nothingShown: 'Nada de tus notas se muestra hasta que hayas escrito.',
    understood: (pct: number) =>
      `Cubrió el ${pct}% de lo que tu material dice sobre esto.`,
    nothingMissing:
      'Nada falta respecto a tu material. Es un resultado real, no una formalidad — la prueba más dura es explicarlo de nuevo en una semana.',
    counted: (concept: string) =>
      `Esto contó para ${concept} — explicar sin apoyo pesa como un ítem difícil.`,
    findings: {
      gaps: 'Afirmado sin justificar',
      oversimplifications: 'Cierto solo en un caso especial',
      assumed: 'Asumido sin nombrar',
      contradictions: 'No pueden ser ambos ciertos',
    },
  },

  socratic: {
    title: 'Socrático',
    lede: 'Recibirás preguntas, una a la vez, y nunca la respuesta. Termina cuando tú mismo hayas dicho la cosa — que te la digan y asentir no cuenta.',
    noConcepts: 'Ningún concepto todavía. Vienen de los documentos que subes.',
    couldNotLoad: 'No se pudieron cargar tus conceptos.',
    couldNotContinue: 'El diálogo no pudo continuar.',
    thinking: 'Pensando…',
    you: 'Tú',
    replyPlaceholder: 'Responde con tus palabras.',
    answer: 'Responder',
    gotThere: 'Llegaste tú solo — la única forma de que esto termine bien.',
    exhausted: 'Hasta aquí llegó por hoy. Lo que mostraste contó igual.',
    recorded: 'Registrado.',
  },

  graph: {
    title: 'Grafo',
    depth: 'Profundidad',
    couldNotLoadConcepts: 'No se pudieron cargar tus conceptos.',
    couldNotLoadGraph: 'No se pudo cargar el grafo.',
    emptyTitle: 'Ningún concepto todavía.',
    emptyBody:
      'Los conceptos y las conexiones entre ellos se extraen de los documentos que subes. Cuando un cuaderno tenga material, esto se llena.',
    startSomewhere: 'Empieza por algún lado',
    allConcepts: 'Todos los conceptos',
    graphLabel: (nodes: number, edges: number) =>
      `Grafo de conceptos: ${nodes} conceptos, ${edges} conexiones`,
    nodeUnscored: (name: string) => `${name}, aún sin puntuar`,
    nodeScored: (name: string, score: number) => `${name}, dominio ${score}`,
  },

  tutor: {
    title: 'Tutor',
    emptyLede:
      'Pregunta sobre este cuaderno. Con documentos indexados, las respuestas citan la página de donde vienen — y avisan cuando la respuesta no está en tu material.',
    you: 'Tú',
    placeholder: 'Pregúntale a NOEMA…',
    unavailable: 'El tutor no está disponible.',
    modes: {
      explain: { label: 'Explicar', blurb: 'Respuestas directas, ejemplos resueltos.' },
      socratic: { label: 'Socrático', blurb: 'Solo preguntas. Tú llegas a la respuesta.' },
      examiner: { label: 'Examinador', blurb: 'Te evalúa. Sin pistas.' },
      study_partner: { label: 'Compañero', blurb: 'Piensa contigo.' },
      feynman: { label: 'Feynman', blurb: 'Tú explicas. Él encuentra los huecos.' },
    },
  },
};
