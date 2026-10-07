# Yerel kurulum ve çalıştırma kısayolları. Önce: make setup
PY := .venv/bin
INTENT ?= Kullanıcı ağından veritabanı sunucusuna (10.20.20.30) tcp/5432 aç
SNAPSHOT ?= examples/acme

.PHONY: setup batfish test live-test demo plan site site-build

setup:            ## Python ortamını kur
	python3 -m venv .venv
	$(PY)/pip install -q -e ".[dev]"

batfish:          ## Batfish'i Docker'da başlat ve hazır olmasını bekle
	docker compose up -d
	@for i in $$(seq 1 60); do \
	  $(PY)/python -c "from pybatfish.client.session import Session; Session(host='localhost')" 2>/dev/null && echo "Batfish hazır" && exit 0; \
	  sleep 3; \
	done; echo "Batfish başlamadı"; exit 1

test: batfish     ## Tüm testler (Batfish dahil)
	BATFISH_HOST=localhost $(PY)/pytest -q

live-test: batfish ## Gerçek Claude + Batfish (ANTHROPIC_API_KEY gerekir, ücretli)
	BATFISH_HOST=localhost $(PY)/pytest -q -s -m claude

demo: batfish     ## API anahtarı olmadan: önce ret, sonra kabul
	$(PY)/kanit plan "$(INTENT)" --snapshot $(SNAPSHOT) \
	  --scripted examples/acme/scripted/01-fazla-genis.json examples/acme/scripted/02-dogru.json

plan: batfish     ## Claude ile (ANTHROPIC_API_KEY gerekir). Örn: make plan INTENT="..."
	$(PY)/kanit plan "$(INTENT)" --snapshot $(SNAPSHOT)

site:             ## Tanıtım sitesini yerelde aç (http://localhost:3000)
	cd site && npm install && npm run dev

site-build:       ## Üretim derlemesi (vinext): site/dist/
	cd site && npm ci && npm run build
