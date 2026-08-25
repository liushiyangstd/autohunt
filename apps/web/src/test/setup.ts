import '@testing-library/jest-dom/vitest';

// jsdom 环境补丁
if (!window.matchMedia) {
  window.matchMedia = ((q: string) => ({
    matches: false, media: q, addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false, onchange: null,
  })) as never;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
