import { render, screen } from '@testing-library/react';
import App from './App';

// CRA's Jest 27 cannot resolve React Router 7's exports; use its real core module.
jest.mock('react-router-dom', () => require('react-router'), { virtual: true });

jest.mock('./components/RequireAuth', () => ({ RequireAuth: ({ children }: any) => children }));
jest.mock('./pages/Login', () => () => <div>Login</div>);
jest.mock('./pages/AuthDebug', () => () => <div>Auth debug</div>);
jest.mock('./pages/Navigator', () => function Navigator() {
  const location = require('react-router-dom').useLocation();
  return <div>Navigator {location.pathname}{location.search}{location.hash}</div>;
});

test('the site root opens Navigator', () => {
  window.history.replaceState({}, '', '/');
  render(<App />);
  expect(screen.getByText('Navigator /')).toBeInTheDocument();
});

test('old Navigator bookmarks redirect and keep query parameters and anchors', () => {
  window.history.replaceState({}, '', '/navigator/companies?search=abc#row');
  render(<App />);
  expect(screen.getByText('Navigator /companies?search=abc#row')).toBeInTheDocument();
  expect(window.location.pathname).toBe('/companies');
});

test('the old storage shortcut opens the Bronze page', () => {
  window.history.replaceState({}, '', '/storage-browser');
  render(<App />);
  expect(screen.getByText('Navigator /file-browser-bronze')).toBeInTheDocument();
});
