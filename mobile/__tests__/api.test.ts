import { api, BASE_URL } from '../src/lib/api';

const mockBlob = jest.fn().mockResolvedValue(new Blob(['fake-image'], { type: 'image/jpeg' }));
const defaultResponse = {
  ok: true,
  json: async () => ({}),
  text: async () => '',
  blob: mockBlob,
};
const mockFetch = jest.fn().mockResolvedValue(defaultResponse);
global.fetch = mockFetch;
global.__DEV__ = true;

describe('Mentis API Client — V1 Methods', () => {

  beforeEach(() => {
    mockFetch.mockReset();
  });

  // ── teachDoubt ────────────────────────────────────────────────────────

  it('teachDoubt sends POST to V1 doubt endpoint', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'ses_123',
        explanation: 'First, let us look at the equation.',
        board_actions: [{ text: 'x = 5', action: 'write', color: '#00E5FF' }],
        key_points: ['Isolate x', 'Divide both sides'],
        quiz: null,
        homework: [],
      }),
    });

    const result = await api.teachDoubt('Solve 2x + 3 = 7', 'math', 'beginner');
    expect(mockFetch).toHaveBeenCalledWith(
      `${BASE_URL}/api/v1/teach/doubt`,
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: expect.stringContaining('Solve 2x + 3 = 7'),
      }),
    );
    expect(result.session_id).toBe('ses_123');
    expect(result.explanation).toBeTruthy();
    expect(result.key_points).toHaveLength(2);
  });

  it('teachDoubt throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      text: async () => 'Bad Request',
    });
    await expect(api.teachDoubt('')).rejects.toThrow();
  });

  // ── teachDoubtWithImage ────────────────────────────────────────────────

  it('teachDoubtWithImage sends POST with FormData', async () => {
    // First call: appendImage fetches the URI to get a blob
    mockFetch.mockResolvedValueOnce({
      ok: true,
      blob: mockBlob,
    });
    // Second call: the actual POST to /api/v1/teach/doubt/image
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'ses_img_456',
        explanation: 'From your image, I can see...',
        concepts: ['quadratic', 'factoring'],
        teaching_decision: { confidence: 0.85 },
      }),
    });

    const result = await api.teachDoubtWithImage('data:image/jpeg;base64,/9j/4AAQ', 'math', 'intermediate');
    expect(mockFetch).toHaveBeenCalledWith(
      `${BASE_URL}/api/v1/teach/doubt/image`,
      expect.objectContaining({ method: 'POST' }),
    );
    expect(result.session_id).toBe('ses_img_456');
    expect(result.concepts).toContain('quadratic');
  });

  it('teachDoubtWithImage returns error detail on failure', async () => {
    // First call: appendImage fetches the URI to get a blob
    mockFetch.mockResolvedValueOnce({
      ok: true,
      blob: mockBlob,
    });
    // Second call: the actual POST which fails
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Image too blurry' }),
    });
    await expect(api.teachDoubtWithImage('bad-image')).rejects.toThrow('Image too blurry');
  });

  // ── teachLesson ────────────────────────────────────────────────────────

  it('teachLesson sends POST to V1 lesson endpoint', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'les_789',
        explanation: 'Let us learn about photosynthesis.',
        key_points: ['Light reaction', 'Calvin cycle'],
      }),
    });

    const result = await api.teachLesson('Photosynthesis', 'beginner', 'science');
    expect(mockFetch).toHaveBeenCalledWith(
      `${BASE_URL}/api/v1/teach/lesson`,
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('Photosynthesis'),
      }),
    );
    expect(result.session_id).toBe('les_789');
  });

  // ── saveSessionV1 ──────────────────────────────────────────────────────

  it('saveSessionV1 sends POST with form data', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 'saved_001' }),
    });

    const result = await api.saveSessionV1({
      userId: 'user_1',
      sessionId: 'ses_123',
      problemTitle: 'Quadratic Equation',
      problemType: 'doubt',
      extractedText: 'Solve x^2 - 5x + 6 = 0',
      explanation: 'First, factor the equation.',
      keyPoints: ['Factor', 'Solve'],
      concepts: ['quadratic'],
      homework: [{ title: 'Practice Q1', description: 'Solve x^2 - 4 = 0' }],
      quiz: { question: 'What is factoring?', options: [], correct_answer: '', explanation: '' },
      memoryUpdate: {},
    });
    expect(result.id).toBe('saved_001');
  });

  // ── listSessionsV1 ─────────────────────────────────────────────────────

  it('listSessionsV1 fetches sessions for user', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        sessions: [
          { id: '1', problemTitle: 'Quadratic', status: 'completed' },
          { id: '2', problemTitle: 'Calculus', status: 'completed' },
        ],
      }),
    });

    const result = await api.listSessionsV1('user_1', 10);
    expect(result.sessions).toHaveLength(2);
    expect(result.sessions[0].problemTitle).toBe('Quadratic');
  });

  // ── getMemory ──────────────────────────────────────────────────────────

  it('getMemory returns user memory data', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        totalSessions: 5,
        streak: 3,
        topTopics: [['algebra', 4], ['calculus', 1]],
      }),
    });

    const result = await api.getMemory('user_1');
    expect(result.totalSessions).toBe(5);
    expect(result.streak).toBe(3);
    expect(result.recentTopics).toContain('algebra');
  });

  it('getMemory returns defaults on failure', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false });
    const result = await api.getMemory('user_1');
    expect(result.totalSessions).toBe(0);
    expect(result.weakTopics).toEqual([]);
  });

  // ── teachDoubtStream ────────────────────────────────────────────────────

  it('teachDoubtStream creates a WebSocket', async () => {
    // Mock WebSocket
    const mockWs = {
      onopen: null as any,
      onerror: null as any,
      close: jest.fn(),
    } as any;
    (global as any).WebSocket = jest.fn(() => mockWs);

    const wsPromise = api.teachDoubtStream('ws://localhost:8000/api/v1/teach/stream');
    // Manually trigger onopen
    setTimeout(() => mockWs.onopen?.(), 0);
    const ws = await wsPromise;
    expect(ws).toBe(mockWs);
  });

  it('teachDoubtStream rejects on error', async () => {
    const mockWs = {
      onopen: null as any,
      onerror: null as any,
    } as any;
    (global as any).WebSocket = jest.fn(() => mockWs);

    const wsPromise = api.teachDoubtStream('ws://localhost:8000/api/v1/teach/stream');
    setTimeout(() => mockWs.onerror?.(), 0);
    await expect(wsPromise).rejects.toThrow('WebSocket connection failed');
  });

  // ── Legacy API methods ─────────────────────────────────────────────────

  it('recognizeProblem sends image to vision endpoint', async () => {
    // First call: appendImage fetches the URI to get a blob
    mockFetch.mockResolvedValueOnce({
      ok: true,
      blob: mockBlob,
    });
    // Second call: the actual POST to /api/tutor/recognize
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        type: 'math',
        title: 'Quadratic Equation',
        content: 'x^2 - 5x + 6 = 0',
        difficulty: 'easy',
      }),
    });

    const result = await api.recognizeProblem('data:image/jpeg;base64,abc', 'math');
    expect(result.type).toBe('math');
    expect(result.content).toContain('x^2');
  });

  it('getStats fetches user stats', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        totalSessions: 10,
        completedSessions: 8,
        topTopics: [['algebra', 5], ['geometry', 3]],
      }),
    });

    const result = await api.getStats('user_1');
    expect(result.totalSessions).toBe(10);
    expect(result.completedSessions).toBe(8);
  });

  it('getStreak fetches streak data', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ streak: 5, lastActive: '2026-07-10' }),
    });

    const result = await api.getStreak('user_1');
    expect(result.streak).toBe(5);
  });

  it('saveSession sends session data', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 'session_1' }),
    });

    const result = await api.saveSession({
      userId: 'u1',
      problemTitle: 'Test',
      problemType: 'math',
      extractedText: 'content',
      status: 'completed',
      steps: '[]',
    });
    expect(result.id).toBe('session_1');
  });

  it('listSessions fetches user session list', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ sessions: [{ id: '1' }, { id: '2' }] }),
    });

    const result = await api.listSessions('user_1');
    expect(result.sessions).toHaveLength(2);
  });

  it('transcribeAudio sends audio file', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ text: 'Hello teacher' }),
    });
    const result = await api.transcribeAudio('file:///recording.m4a');
    expect(result.text).toBe('Hello teacher');
  });

  it('getStepHelp sends step context', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ help: 'Try isolating the variable' }),
    });
    const result = await api.getStepHelp('math', '2x+3=7', [], {});
    expect(result.help).toBeTruthy();
  });

  it('askDoubt sends doubt question', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        reply: 'Good question! Look at the coefficient.',
        pen_annotation: 'Circle the x term',
        follow_up: 'What operation isolates x?',
      }),
    });
    const result = await api.askDoubt({
      content: '2x + 3 = 7',
      question: 'Why do we subtract 3?',
    });
    expect(result.reply).toContain('Good question');
    expect(result.pen_annotation).toBeTruthy();
    expect(result.follow_up).toBeTruthy();
  });

  it('createSessionPdf sends session data', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        filename: 'session.pdf',
        mime: 'application/pdf',
        base64: 'JVBERi0...',
      }),
    });
    const result = await api.createSessionPdf({
      title: 'Algebra',
      problem: '2x+3=7',
      steps: [],
      transcript: [],
      penNotes: [],
    });
    expect(result.filename).toBe('session.pdf');
  });
});
