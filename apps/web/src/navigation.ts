import { useEffect, useState } from 'react';

type RouteWithSearch = { search?: string };

export type AppRoute =
  | ({ name: 'today' } & RouteWithSearch)
  | ({ name: 'inbox'; candidateId?: string } & RouteWithSearch)
  | ({ name: 'matters'; matterId?: string } & RouteWithSearch)
  | ({ name: 'reviews'; reviewPackageId?: string } & RouteWithSearch)
  | ({ name: 'templates' } & RouteWithSearch)
  | ({ name: 'files' } & RouteWithSearch)
  | ({ name: 'agent-runs'; runId?: string } & RouteWithSearch)
  | ({ name: 'data-boundaries' } & RouteWithSearch)
  | ({ name: 'about' } & RouteWithSearch)
  | ({ name: 'not-found'; pathname: string } & RouteWithSearch);

type LocationLike = Pick<Location, 'pathname' | 'search'>;
type NavigateOptions = { replace?: boolean; state?: unknown };

const navigationEvent = 'legal-workbench:navigate';

function decodeSegment(segment: string | undefined): string | undefined {
  if (!segment) return undefined;
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

function normalizedSearch(search?: string): string {
  if (!search) return '';
  return search.startsWith('?') ? search : `?${search}`;
}

export function parseLocation(location: LocationLike): AppRoute {
  const pathname = location.pathname.replace(/\/+$/, '') || '/';
  const segments = pathname.split('/').filter(Boolean);
  const search = location.search;

  if (pathname === '/' || pathname === '/today') return { name: 'today', search };
  if (segments[0] === 'inbox' && segments.length <= 2) {
    return { name: 'inbox', candidateId: decodeSegment(segments[1]), search };
  }
  if (segments[0] === 'matters' && segments.length <= 2) {
    return { name: 'matters', matterId: decodeSegment(segments[1]), search };
  }
  if (segments[0] === 'reviews' && segments.length <= 2) {
    return { name: 'reviews', reviewPackageId: decodeSegment(segments[1]), search };
  }
  if (pathname === '/templates') return { name: 'templates', search };
  if (pathname === '/files') return { name: 'files', search };
  if (segments[0] === 'system' && segments[1] === 'agent-runs' && segments.length <= 3) {
    return { name: 'agent-runs', runId: decodeSegment(segments[2]), search };
  }
  if (pathname === '/system/data-boundaries') return { name: 'data-boundaries', search };
  if (pathname === '/system/about') return { name: 'about', search };
  return { name: 'not-found', pathname, search };
}

export function buildPath(route: AppRoute): string {
  const search = normalizedSearch(route.search);
  switch (route.name) {
    case 'today': return `/today${search}`;
    case 'inbox': return `/inbox${route.candidateId ? `/${encodeURIComponent(route.candidateId)}` : ''}${search}`;
    case 'matters': return `/matters${route.matterId ? `/${encodeURIComponent(route.matterId)}` : ''}${search}`;
    case 'reviews': return `/reviews${route.reviewPackageId ? `/${encodeURIComponent(route.reviewPackageId)}` : ''}${search}`;
    case 'templates': return `/templates${search}`;
    case 'files': return `/files${search}`;
    case 'agent-runs': return `/system/agent-runs${route.runId ? `/${encodeURIComponent(route.runId)}` : ''}${search}`;
    case 'data-boundaries': return `/system/data-boundaries${search}`;
    case 'about': return `/system/about${search}`;
    case 'not-found': return `${route.pathname}${search}`;
  }
}

export function navigate(path: string, options: NavigateOptions = {}): void {
  const method = options.replace ? 'replaceState' : 'pushState';
  window.history[method](options.state ?? null, '', path);
  window.dispatchEvent(new Event(navigationEvent));
}

export function useAppLocation(): AppRoute {
  const [route, setRoute] = useState<AppRoute>(() => parseLocation(window.location));

  useEffect(() => {
    const update = () => setRoute(parseLocation(window.location));
    window.addEventListener('popstate', update);
    window.addEventListener(navigationEvent, update);
    return () => {
      window.removeEventListener('popstate', update);
      window.removeEventListener(navigationEvent, update);
    };
  }, []);

  return route;
}
