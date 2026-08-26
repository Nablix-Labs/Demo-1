/**
 * fetchWorkArtifactPdfUrl — fetches the logical pdf_url as a Blob through the
 * shared api client (so baseURL + the auth interceptor apply, which a raw
 * iframe src never could) and returns an object URL.
 *
 * jsdom has no URL.createObjectURL, so it's stubbed here rather than adding
 * @testing-library/react + a .tsx test config just for this.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const get = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: (...args: unknown[]) => get(...args) },
}));

describe('fetchWorkArtifactPdfUrl', () => {
  const originalCreateObjectURL = URL.createObjectURL;

  beforeEach(() => {
    get.mockReset();
    URL.createObjectURL = vi.fn(() => 'blob:mock-object-url');
  });

  afterEach(() => {
    URL.createObjectURL = originalCreateObjectURL;
  });

  it('fetches the logical url as a blob and returns an object url', async () => {
    const { fetchWorkArtifactPdfUrl } = await import('@/lib/workArtifactPdf');
    const blob = new Blob(['%PDF-1.4 fake'], { type: 'application/pdf' });
    get.mockResolvedValue({ data: blob });

    const result = await fetchWorkArtifactPdfUrl('/work-artifacts/ART-1/pdf');

    expect(get).toHaveBeenCalledWith('/work-artifacts/ART-1/pdf', { responseType: 'blob' });
    expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
    expect(result).toBe('blob:mock-object-url');
  });

  it('propagates a failed fetch rather than returning a broken url', async () => {
    const { fetchWorkArtifactPdfUrl } = await import('@/lib/workArtifactPdf');
    get.mockRejectedValue(new Error('Request failed with status code 404'));

    await expect(fetchWorkArtifactPdfUrl('/work-artifacts/ART-999/pdf')).rejects.toThrow(
      'Request failed with status code 404',
    );
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
