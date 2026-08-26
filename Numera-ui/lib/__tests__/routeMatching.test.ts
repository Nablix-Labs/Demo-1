import { describe, expect, it } from 'vitest';

/**
 * Mirrors AppFrame's route lists and matcher.
 *
 * Kept as a plain unit test rather than a render test because the bug was never
 * about rendering: the predicate returned false on a path shape that only the
 * export build produces, so a dev-server render test would have passed while
 * the deployed site was broken.
 */
const TUTORING_ROUTES = ['/', '/practice'];
const FOCUS_ROUTES = ['/onboard', '/diagnostic', '/orientation', '/teach', '/complete', '/consent', '/login', '/restricted', '/dev-screens'];

function matchesRoute(pathname: string, route: string): boolean {
  return pathname === route || pathname.startsWith(`${route}/`);
}

const tutoring = (p: string) => TUTORING_ROUTES.some((r) => matchesRoute(p, r));
const focus = (p: string) => FOCUS_ROUTES.some((r) => matchesRoute(p, r));

describe('tutoring routes with export trailing slashes', () => {
  it('matches /practice/ as served by the static export', () => {
    // The regression: bare === was false here, so the dock never auto-hid and
    // covered the canvas toolbar on the live site.
    expect(tutoring('/practice/')).toBe(true);
  });

  it('still matches the dev-server form', () => {
    expect(tutoring('/practice')).toBe(true);
  });

  it('matches the lesson root', () => {
    expect(tutoring('/')).toBe(true);
  });

  it('does not treat every route as a tutoring route', () => {
    // '/' must not match via the startsWith arm, or the dock would auto-hide
    // everywhere and navigation would vanish across the whole app.
    for (const p of ['/workbook/', '/history/', '/profile/', '/review/', '/keynotes/']) {
      expect(tutoring(p)).toBe(false);
    }
  });

  it('does not match a route that merely shares a prefix', () => {
    expect(tutoring('/practices/')).toBe(false);
  });
});

describe('focus routes', () => {
  it('matches both slash forms and nested topics', () => {
    expect(focus('/diagnostic/')).toBe(true);
    expect(focus('/diagnostic')).toBe(true);
    expect(focus('/diagnostic/algebra/')).toBe(true);
  });

  it('leaves ordinary in-app routes alone', () => {
    expect(focus('/workbook/')).toBe(false);
  });
});
