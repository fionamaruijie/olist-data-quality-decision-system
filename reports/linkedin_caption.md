# LinkedIn caption

**A dashboard is only as useful as the data behind it.**

I took the Olist Brazilian e-commerce dataset — 9 tables, ~100k orders — and asked a simple question before touching a single chart: can these numbers be trusted?

They couldn't, not yet. A naive join of orders × items × payments quietly **double-counts revenue** (inflating cash collected by 27%), the geolocation table repeats 1,000,163 rows for just 19,015 postal codes, and every customer gets a brand-new ID on every order — so "repeat rate" is meaningless until you resolve identity. Fix those three things first, and the dataset becomes decision-ready.

Then the story gets clear and consistent:

📦 **Delivery time is the strongest operational signal associated with low review scores** (r = −0.33). Five-star orders arrive in ~11 days; one-star orders take ~21.
🛍️ **Revenue is concentrated** — 18 of 74 categories make 80% of it, and São Paulo alone is 38%.
🔁 **Only 3% of customers come back.** This is an acquisition engine, not a retention engine.

I also ran an **AI-augmented** step that I could actually defend: an LLM classified 1,000 review comments by topic and sentiment, and I validated it against a second, independent LLM annotator (κ = 0.81–0.89) and against the star ratings the model never saw (83% agreement). The result corrected my own assumption — product-quality complaints slightly outnumber delivery ones — but delivery complaints were the ones provably tied to slow shipping (26 days vs 13).

The deliverable isn't the dashboard. It's the **traceable data layer** underneath it — because that's what makes a recommendation defensible.

Built with Python, DuckDB, SQL checks, reproducible documentation, and an AI-assisted review-classification step. Data: Olist via Kaggle (CC BY-NC 4.0).

#DataAnalytics #BusinessIntelligence #DataQuality #Ecommerce #Analytics #AI
