/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** Asistan API'si (LLM + kural motoru + [D]/[K] kaynakları), örn. http://192.168.1.12:8000 — sadece legacy ekran */
  readonly VITE_ASSISTANT_API_URL?: string;
  /** Boşsa asistan API'sinin seçili astronotu kullanılır */
  readonly VITE_ASSISTANT_ASTRONAUT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
