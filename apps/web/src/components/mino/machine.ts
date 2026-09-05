/**
 * Mino's state machine: what the character can be doing, how it gets there,
 * and what each state looks like on the rig.
 *
 * The UI never names an animation. It says what is happening (an input was
 * focused, a request started, an answer was wrong) and the controller turns
 * that into a state; the state resolves to a pose here. Rendering, timing and
 * springs live elsewhere. Nothing in this file touches the DOM.
 */

export type MinoState =
  | 'idle'
  | 'curious'
  | 'listening'
  | 'thinking'
  | 'teaching'
  | 'pointing'
  | 'reading'
  | 'writing'
  | 'happy'
  | 'celebrating'
  | 'sleepy'
  | 'confused'
  | 'wave'
  // The professor's moves (V3): what the lesson is doing right now, said by
  // the server. Distinct poses, because asking, correcting and sitting an
  // exam are not the same act as explaining.
  | 'questioning'
  | 'correcting'
  | 'exam'
  | 'concerned'
  // Kept for existing screens; each is a named alias of a pose above.
  | 'reviewing'
  | 'focused'
  | 'sleeping';

export type Mouth = 'neutral' | 'smile' | 'open' | 'think' | 'o' | 'flat';
export type Hands = 'rest' | 'point' | 'wave' | 'hold' | 'chin' | 'up' | 'write';

/** What the rig draws. Every field is a small, bounded number or a name. */
export interface Pose {
  /** Where the eyes look, -1..1 on both axes; the head follows a fraction. */
  gaze: { x: number; y: number };
  /** Head turn (-1 left … 1 right) and tilt in degrees, both small. */
  turn: number;
  tilt: number;
  /** Eye openness, 0 (shut) to 1. Blinks are layered on top by the controller. */
  eyes: number;
  /** Happy eyes curve upward; 0 none, 1 full. */
  squint: number;
  mouth: Mouth;
  hands: Hands;
  /** Body lean, -1 back … 1 forward; small. */
  lean: number;
  /** Extra lift of the whole figure (celebrate), px in rig units. */
  lift: number;
}

const BASE: Pose = {
  gaze: { x: 0, y: 0 },
  turn: 0,
  tilt: 0,
  eyes: 1,
  squint: 0,
  mouth: 'neutral',
  hands: 'rest',
  lean: 0,
  lift: 0,
};

/** The pose each state settles into. Motion between them is the controller's. */
export const POSES: Record<MinoState, Pose> = {
  idle: { ...BASE, mouth: 'smile', squint: 0.1 },
  curious: { ...BASE, tilt: -5, gaze: { x: 0.25, y: -0.1 }, mouth: 'o', squint: 0 },
  listening: { ...BASE, tilt: 4, turn: 0.15, gaze: { x: 0.35, y: 0.2 }, mouth: 'neutral', lean: 0.3 },
  thinking: { ...BASE, tilt: 6, gaze: { x: -0.4, y: -0.6 }, mouth: 'think', hands: 'chin', lean: -0.1 },
  teaching: { ...BASE, turn: -0.1, gaze: { x: 0.2, y: 0.1 }, mouth: 'open', hands: 'point', lean: 0.2 },
  pointing: { ...BASE, turn: 0.2, gaze: { x: 0.6, y: 0 }, mouth: 'smile', hands: 'point', lean: 0.2 },
  reading: { ...BASE, tilt: 3, gaze: { x: 0, y: 0.7 }, mouth: 'neutral', hands: 'hold', lean: 0.2 },
  writing: { ...BASE, tilt: 4, gaze: { x: 0.2, y: 0.7 }, mouth: 'flat', hands: 'write', lean: 0.3 },
  happy: { ...BASE, mouth: 'smile', squint: 0.7, tilt: -2 },
  celebrating: { ...BASE, mouth: 'open', squint: 0.8, hands: 'up', lift: -8, tilt: -3 },
  sleepy: { ...BASE, eyes: 0.15, mouth: 'flat', tilt: 8, lean: -0.2, gaze: { x: 0, y: 0.4 } },
  confused: { ...BASE, tilt: -9, gaze: { x: 0.3, y: -0.2 }, mouth: 'flat', squint: 0 },
  wave: { ...BASE, mouth: 'smile', squint: 0.4, hands: 'wave', tilt: -3 },
  // The moves. Questioning leans in with a raised brow of a tilt; correcting
  // is calm and level, pointing at the thing; the exam pose sits back with
  // the card in both hands; concerned is a small frown, never alarm.
  questioning: { ...BASE, tilt: -6, turn: 0.1, gaze: { x: 0.3, y: 0.1 }, mouth: 'o', hands: 'point', lean: 0.3 },
  correcting: { ...BASE, tilt: 0, gaze: { x: 0.15, y: 0.15 }, mouth: 'neutral', hands: 'point', lean: 0.15 },
  exam: { ...BASE, tilt: 2, gaze: { x: 0, y: 0.5 }, mouth: 'flat', hands: 'hold', lean: -0.1 },
  concerned: { ...BASE, tilt: 5, gaze: { x: 0.1, y: 0.2 }, mouth: 'think', hands: 'chin', lean: 0.1, squint: 0 },
  // Aliases.
  reviewing: { ...BASE, tilt: 2, gaze: { x: 0.1, y: 0.5 }, mouth: 'neutral', hands: 'hold', lean: 0.15 },
  focused: { ...BASE, gaze: { x: 0.1, y: 0.3 }, mouth: 'flat', lean: 0.25, squint: 0.2 },
  sleeping: { ...BASE, eyes: 0, mouth: 'flat', tilt: 10, lean: -0.3 },
};

/**
 * What the UI is allowed to say. The bridge from product events to states —
 * a screen calls `mino.on('input_focus')`, never `mino.setState('curious')`
 * unless it is deliberately scripting the character (a storyboard section).
 */
export type MinoEvent =
  | 'input_focus'
  | 'input_blur'
  | 'input_typing'
  | 'input_pause'
  | 'input_submit'
  | 'request_started'
  | 'response_streaming'
  | 'response_done'
  | 'exercise_correct'
  | 'exercise_wrong'
  | 'read'
  | 'write'
  | 'point'
  | 'greet'
  | 'lost'
  | 'idle_timeout'
  | 'reset';

export const EVENT_TO_STATE: Record<MinoEvent, MinoState> = {
  input_focus: 'curious',
  input_blur: 'idle',
  input_typing: 'listening',
  input_pause: 'thinking',
  input_submit: 'thinking',
  request_started: 'thinking',
  response_streaming: 'teaching',
  response_done: 'idle',
  exercise_correct: 'happy',
  exercise_wrong: 'thinking',
  read: 'reading',
  write: 'writing',
  point: 'pointing',
  greet: 'wave',
  lost: 'confused',
  idle_timeout: 'sleepy',
  reset: 'idle',
};

/**
 * States that are a reaction, not a place to stay: they return to `after`
 * once `ms` has passed unless something else happens first. A correct answer
 * earns one short happy moment, not a permanent grin.
 */
export const TRANSIENT: Partial<Record<MinoState, { ms: number; after: MinoState }>> = {
  happy: { ms: 1400, after: 'idle' },
  celebrating: { ms: 1600, after: 'happy' },
  wave: { ms: 1800, after: 'idle' },
  confused: { ms: 2400, after: 'curious' },
};

/**
 * The states the server may name in a `mino` event. Anything else is
 * ignored: the interface never lets a payload invent a pose.
 */
export const SERVER_STATES: Record<string, MinoState> = {
  idle: 'idle',
  thinking: 'thinking',
  teaching: 'teaching',
  questioning: 'questioning',
  correcting: 'correcting',
  reviewing: 'reviewing',
  writing: 'writing',
  exam: 'exam',
  happy: 'happy',
  celebrating: 'celebrating',
  concerned: 'concerned',
  listening: 'listening',
};

/** Whether the eyes may follow the pointer in this state. */
export function tracksPointer(state: MinoState): boolean {
  return state === 'idle' || state === 'curious' || state === 'happy' || state === 'wave';
}
