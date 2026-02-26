# Streaming Service Toggles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a toggle bar above the film grid so users can select which streaming services they subscribe to, splitting the grid into "Streaming on your services" and "Everything else" sections.

**Architecture:** Pure client-side filtering using vanilla JS and localStorage. The server computes a deduplicated platform list at render time and embeds it in the template. JS reads toggle state from localStorage, classifies film cards by their `data-platform-ids` attribute, and moves them between two `<section>` elements in the DOM. No new endpoints.

**Tech Stack:** FastAPI + Jinja2 (server), vanilla JS + localStorage (client), CSS transitions.

---

### Task 1: Python helper + route update

**Files:**
- Modify: `main.py`
- Test: `tests/test_routes.py`

**Step 1: Write the failing tests**

Add to `tests/test_routes.py`:

```python
def test_get_all_platforms_deduplicates_and_sorts():
    from main import _get_all_platforms
    films = [
        Film(
            letterboxd_slug="a",
            title="A",
            streaming_platforms=[
                StreamingPlatform(provider_id=8, provider_name="Netflix"),
                StreamingPlatform(provider_id=337, provider_name="Disney+"),
            ],
        ),
        Film(
            letterboxd_slug="b",
            title="B",
            streaming_platforms=[
                StreamingPlatform(provider_id=8, provider_name="Netflix"),  # duplicate
                StreamingPlatform(provider_id=2100, provider_name="Apple TV+"),
            ],
        ),
    ]
    result = _get_all_platforms(films)
    assert len(result) == 3
    assert [p.provider_name for p in result] == ["Apple TV+", "Disney+", "Netflix"]


def test_get_all_platforms_empty():
    from main import _get_all_platforms
    assert _get_all_platforms([]) == []


def test_index_passes_all_platforms_to_template(client):
    films = [
        Film(
            letterboxd_slug="oppenheimer-2023",
            title="Oppenheimer",
            tmdb_status="found",
            streaming_platforms=[StreamingPlatform(provider_id=8, provider_name="Netflix")],
        )
    ]
    with (
        patch("main.database.get_all_films", new=AsyncMock(return_value=films)),
        patch("main.database.get_last_updated", new=AsyncMock(return_value=None)),
    ):
        response = client.get("/")
    assert response.status_code == 200
    assert 'data-provider-id="8"' in response.text
    assert 'data-platform-ids="8"' in response.text
```

**Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_routes.py::test_get_all_platforms_deduplicates_and_sorts tests/test_routes.py::test_get_all_platforms_empty tests/test_routes.py::test_index_passes_all_platforms_to_template -v
```

Expected: FAIL (ImportError or AttributeError — `_get_all_platforms` does not exist yet)

**Step 3: Add helper and update route in `main.py`**

Add after the imports, before `lifespan`:

```python
def _get_all_platforms(films: list) -> list:
    seen: dict = {}
    for film in films:
        for p in film.streaming_platforms:
            if p.provider_id not in seen:
                seen[p.provider_id] = p
    return sorted(seen.values(), key=lambda p: p.provider_name)
```

Update the index route to compute and pass `all_platforms`:

```python
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    films = await database.get_all_films()
    last_updated = await database.get_last_updated()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "films": films,
            "last_updated": last_updated,
            "is_refreshing": scheduler.get_refresh_state(),
            "all_platforms": _get_all_platforms(films),
        },
    )
```

**Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_routes.py::test_get_all_platforms_deduplicates_and_sorts tests/test_routes.py::test_get_all_platforms_empty tests/test_routes.py::test_index_passes_all_platforms_to_template -v
```

Expected: PASS (3 tests)

**Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: all existing tests still pass.

**Step 6: Commit**

```bash
git add main.py tests/test_routes.py
git commit -m "feat: add _get_all_platforms helper and pass to template"
```

---

### Task 2: Template — toggle bar, data attributes, two-section layout

**Files:**
- Modify: `templates/index.html`

Replace the entire contents of `templates/index.html` with:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Watchlist</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <header>
    <h1>Watchlist</h1>
    <div class="meta">
      {% if last_updated %}
        Last updated: {{ last_updated }}
      {% else %}
        No data yet - trigger a refresh below.
      {% endif %}
    </div>
    <form method="post" action="/refresh">
      <button type="submit" {% if is_refreshing %}disabled{% endif %}>
        {% if is_refreshing %}Refreshing...{% else %}Refresh now{% endif %}
      </button>
    </form>
  </header>

  <main>
    {% if not films %}
      <p class="empty">No films found. Click "Refresh now" to fetch your watchlist.</p>
    {% else %}

      {% if all_platforms %}
      <div class="service-toggles">
        <div class="chips" id="chips">
          {% for p in all_platforms %}
          <button
            class="chip"
            data-provider-id="{{ p.provider_id }}"
            type="button"
            title="{{ p.provider_name }}"
          >
            {% if p.logo_path %}
            <img src="{{ p.logo_path }}" alt="" />
            {% endif %}
            <span>{{ p.provider_name }}</span>
          </button>
          {% endfor %}
        </div>
        <div class="toggle-actions">
          <button type="button" id="select-all" class="btn-text">All</button>
          <button type="button" id="select-none" class="btn-text">None</button>
        </div>
      </div>
      {% endif %}

      <section id="section-streaming" class="film-section" hidden>
        <h2 class="section-heading">Streaming on your services</h2>
        <ul class="film-grid" id="grid-streaming"></ul>
      </section>

      <section id="section-other" class="film-section" hidden>
        <h2 class="section-heading section-heading--dim">Everything else</h2>
        <ul class="film-grid" id="grid-other"></ul>
      </section>

      <ul class="film-grid" id="grid-all">
        {% for film in films %}
        <li
          class="film-card"
          data-platform-ids="{{ film.streaming_platforms | map(attribute='provider_id') | join(',') }}"
          data-index="{{ loop.index0 }}"
        >
          {% if film.poster_url %}
            <img src="{{ film.poster_url }}" alt="{{ film.title }}" loading="lazy" />
          {% else %}
            <div class="no-poster">No poster</div>
          {% endif %}
          <div class="film-info">
            <h2>{{ film.title }}{% if film.year %} <span class="year">({{ film.year }})</span>{% endif %}</h2>
            {% if film.streaming_platforms %}
              <ul class="platforms">
                {% for platform in film.streaming_platforms %}
                <li>
                  {% if platform.logo_path %}
                    <img src="{{ platform.logo_path }}" alt="{{ platform.provider_name }}" title="{{ platform.provider_name }}" />
                  {% else %}
                    {{ platform.provider_name }}
                  {% endif %}
                </li>
                {% endfor %}
              </ul>
            {% elif film.tmdb_status == "not_found" %}
              <p class="unavailable">Not found on TMDB</p>
            {% else %}
              <p class="unavailable">Not streaming in {{ film.country }}</p>
            {% endif %}
          </div>
        </li>
        {% endfor %}
      </ul>

    {% endif %}
  </main>

  <script>
  (function () {
    var STORAGE_KEY = 'watchlist_enabled_services';

    var chips = Array.from(document.querySelectorAll('.chip'));
    var allIds = chips.map(function (c) { return parseInt(c.dataset.providerId); });

    function loadEnabled() {
      try {
        var stored = localStorage.getItem(STORAGE_KEY);
        if (stored === null) return new Set(allIds);
        return new Set(JSON.parse(stored));
      } catch (_) {
        return new Set(allIds);
      }
    }

    function saveEnabled(enabled) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(enabled)));
    }

    var enabled = loadEnabled();

    function applyChips() {
      chips.forEach(function (chip) {
        var id = parseInt(chip.dataset.providerId);
        chip.classList.toggle('active', enabled.has(id));
      });
    }

    function classify() {
      var gridAll = document.getElementById('grid-all');
      var sectionStreaming = document.getElementById('section-streaming');
      var sectionOther = document.getElementById('section-other');
      var gridStreaming = document.getElementById('grid-streaming');
      var gridOther = document.getElementById('grid-other');

      if (!gridAll) return;

      var allCards = Array.from(document.querySelectorAll('.film-card'));

      var allEnabled = allIds.length === 0 || allIds.every(function (id) { return enabled.has(id); });

      if (allEnabled) {
        allCards.sort(function (a, b) { return parseInt(a.dataset.index) - parseInt(b.dataset.index); });
        allCards.forEach(function (card) { gridAll.appendChild(card); });
        if (sectionStreaming) sectionStreaming.hidden = true;
        if (sectionOther) sectionOther.hidden = true;
        gridAll.hidden = false;
      } else {
        var streaming = [], other = [];
        allCards.forEach(function (card) {
          var raw = card.dataset.platformIds || '';
          var ids = raw.split(',').filter(Boolean).map(Number);
          var matches = ids.some(function (id) { return enabled.has(id); });
          (matches ? streaming : other).push(card);
        });

        function byIndex(a, b) { return parseInt(a.dataset.index) - parseInt(b.dataset.index); }
        streaming.sort(byIndex);
        other.sort(byIndex);

        if (gridStreaming) streaming.forEach(function (c) { gridStreaming.appendChild(c); });
        if (gridOther) other.forEach(function (c) { gridOther.appendChild(c); });

        gridAll.hidden = true;
        if (sectionStreaming) sectionStreaming.hidden = streaming.length === 0;
        if (sectionOther) sectionOther.hidden = other.length === 0;
      }
    }

    function update() {
      applyChips();
      classify();
      saveEnabled(enabled);
    }

    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        var id = parseInt(chip.dataset.providerId);
        if (enabled.has(id)) {
          enabled.delete(id);
        } else {
          enabled.add(id);
        }
        update();
      });
    });

    var btnAll = document.getElementById('select-all');
    var btnNone = document.getElementById('select-none');
    if (btnAll) btnAll.addEventListener('click', function () { enabled = new Set(allIds); update(); });
    if (btnNone) btnNone.addEventListener('click', function () { enabled = new Set(); update(); });

    update();
  })();
  </script>
</body>
</html>
```

**Step: Verify template manually**

Start the dev server:
```bash
uv run uvicorn main:app --reload --port 8000
```
Open `http://localhost:8000`. Confirm:
- Page loads without error
- Film grid renders as before (no regressions)
- If DB is populated with films that have streaming platforms, chips appear above the grid

**Step: Run route tests**

```bash
uv run pytest tests/test_routes.py -v
```

Expected: all pass (the template change is backward-compatible — `all_platforms` is now always passed).

**Step: Commit**

```bash
git add templates/index.html
git commit -m "feat: add toggle bar and two-section layout to template"
```

---

### Task 3: CSS — chip styles and section headings

**Files:**
- Modify: `static/style.css`

Append to the end of `static/style.css`:

```css
/* --- Service toggles --- */

.service-toggles {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 2rem;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.chip {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.65rem 0.3rem 0.3rem;
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 999px;
  cursor: pointer;
  font-size: 0.8rem;
  color: #555;
  transition: opacity 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.chip.active {
  color: #e0e0e0;
  border-color: #555;
}

.chip:hover {
  border-color: #666;
  color: #aaa;
}

.chip.active:hover {
  border-color: #888;
  color: #e0e0e0;
}

.chip img {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  opacity: 0.4;
  transition: opacity 0.15s ease;
}

.chip.active img {
  opacity: 1;
}

.toggle-actions {
  display: flex;
  gap: 0.5rem;
  margin-left: auto;
}

.btn-text {
  background: none;
  border: none;
  color: #555;
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0.2rem 0.4rem;
}

.btn-text:hover {
  color: #aaa;
}

/* --- Section headings --- */

.film-section {
  margin-bottom: 2.5rem;
}

.section-heading {
  font-size: 0.7rem;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 1rem;
}

.section-heading--dim {
  color: #3a3a3a;
}
```

**Step: Visual check**

With the dev server running, toggle some chips. Confirm:
- Inactive chips are visually muted (grey text + image, dim border)
- Active chips are bright (white text, full-opacity image, visible border)
- Hovering an inactive chip brightens it (clearly re-selectable)
- "All" / "None" buttons are subtle text links, not heavy buttons
- When a service is deselected, films split into two sections with correct headings

**Step: Commit**

```bash
git add static/style.css
git commit -m "feat: add chip and section heading styles for service toggles"
```

---

### Task 4: Final verification

**Step 1: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

**Step 2: Manual end-to-end check**

With a populated DB:
1. Load the page — chips visible, all active, flat grid (no section headers)
2. Deselect one service — grid splits into two sections
3. Reload the page — split state persists (localStorage)
4. Click "None" — all films in "Everything else"
5. Click "All" — returns to flat grid
6. Re-select a single service — only films on that service appear in section 1

**Step 3: Commit**

```bash
git commit --allow-empty -m "chore: streaming service toggles complete"
```
