import { httpApi } from './client';
import { isMockMode, mockApi } from './mock';

export const api = isMockMode() ? mockApi : httpApi;
export const mockMode = isMockMode();
export * from './types';
export { ApiError, ensureUiSession } from './client';
