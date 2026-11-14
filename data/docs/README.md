# RAG belgeleri

Bu klasöre **gerçek** kaynak belgeler konur (PDF, Markdown, TXT). Örnekler:

- NASA-STD-3001 Volume 1 (Crew Health) ve Volume 2 (Human Factors, Habitability, and Environmental Health)
- NASA Human Research Program (HRP) evidence report'ları
- Mürettebat tıbbi prosedürleri (varsa)

Kurallar:

- Belge içeriği **uydurulmaz**. Test için örnek belge `backend/tests/fixtures/docs/` altındadır.
- Belgeler repoya girmez (`.gitignore`); her makinede ayrıca kopyalanır.
- Belge ekledikten sonra: `cd backend && .venv/Scripts/python -m app.cli reindex`
- Bu `README.md` dosyası indekslenmez.
