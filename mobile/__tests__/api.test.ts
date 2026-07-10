import { api, BASE_URL } from '../src/lib/api';

// Simple validation tests for the API client
describe('API Client', () => {
  it('BASE_URL is defined', () => {
    expect(BASE_URL).toBeDefined();
    expect(BASE_URL.length).toBeGreaterThan(0);
  });

  it('api object has all required methods', () => {
    const methods = [
      'recognizeProblem',
      'generateLesson',
      'getStepHelp',
      'askDoubt',
      'createSessionPdf',
      'transcribeAudio',
      'saveSession',
      'listSessions',
      'getStats',
      'getStreak',
      'getDiscussions',
      'createDiscussion',
      'getStudyGroups',
      'createStudyGroup',
      'teachDoubt',
      'teachDoubtWithImage',
      'teachLesson',
    ];

    for (const method of methods) {
      expect(typeof (api as any)[method]).toBe('function');
    }
  });

  it('teachDoubt sends correct request shape', async () => {
    // Mock fetch to verify request shape
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ session_id: 'test', explanation: 'test' }),
    });
    global.fetch = mockFetch;

    await api.teachDoubt('Solve x+2=5', 'math', 'intermediate');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/v1/teach/doubt');
    expect(options.method).toBe('POST');
    expect(options.headers['Content-Type']).toBe('application/json');

    const body = JSON.parse(options.body);
    expect(body.content).toBe('Solve x+2=5');
    expect(body.mode).toBe('math');
    expect(body.level).toBe('intermediate');
  });

  it('teachLesson sends correct request shape', async () => {
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ session_id: 'test', explanation: 'test' }),
    });
    global.fetch = mockFetch;

    await api.teachLesson('Turing Machine', 'beginner');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/v1/teach/lesson');
    expect(options.method).toBe('POST');

    const body = JSON.parse(options.body);
    expect(body.topic).toBe('Turing Machine');
    expect(body.level).toBe('beginner');
  });
});
