# iXpert - Design System & Project Guide

## Project Overview
iXpert es un portal de documentación/knowledge base para empleados bancarios. Full-stack app con Flask + PostgreSQL desplegado en Render.com via Docker.

## Tech Stack
- **Backend:** Flask + SQLAlchemy + Flask-Login + Gunicorn
- **Database:** PostgreSQL (Render)
- **Frontend:** Jinja2 templates + Vanilla JS
- **CMS Editor:** Quill.js
- **Charts:** Chart.js
- **Deployment:** Docker on Render.com

## Color Palette (CSS Variables)

```css
:root {
    --naranja-itau: #ff6600;    /* Primary: CTA buttons, headers, hover accents */
    --naranja-claro: #ff9500;   /* Gradients, secondary orange */
    --azul-itau: #002776;       /* Dark blue: nav, accordions, headings */
    --azul-medio: #004080;      /* Medium blue: buttons, footer, fixed nav */
    --gris-claro: #f2f2f2;      /* Light backgrounds, alternating rows */
    --gris-fondo: #f4f4f4;      /* Card backgrounds */
    --gris-page: #f9f9f9;       /* Page background */
    --gris-texto: #333333;      /* Body text */
    --gris-meta: #888888;       /* Metadata, secondary text */
    --negro: #000000;           /* Nav bars when needed */
    --blanco: #ffffff;          /* Content backgrounds */
    --sombra-sm: 0 2px 5px rgba(0,0,0,0.1);
    --sombra-md: 0 4px 8px rgba(0,0,0,0.2);
    --sombra-lg: 0 8px 16px rgba(0,0,0,0.2);
    --sombra-naranja: 0 8px 20px rgba(255, 102, 0, 0.4);
}
```

## Typography
- **Primary:** `'Segoe UI', Tahoma, Geneva, Verdana, sans-serif`
- **Secondary:** `'Roboto', sans-serif` (Google Fonts: 400, 700)
- **Fallback:** `Arial, sans-serif`
- **Line height:** 1.6
- **Body text:** 16px, color var(--gris-texto)

## Component Patterns

### Header
```css
background: linear-gradient(135deg, var(--naranja-itau), var(--naranja-claro));
color: var(--blanco);
padding: 20px;
text-align: center;
box-shadow: var(--sombra-md);
```

### Navigation
```css
background-color: var(--azul-medio);
padding: 15px 0;
/* Links: white, 18px, bold, hover → background var(--naranja-itau) */
```

### Cards
```css
background: var(--blanco);
border-radius: 10px;
border: 1px solid var(--naranja-itau);
padding: 20px;
box-shadow: 0 4px 12px rgba(0,0,0,0.1);
transition: transform 0.3s;
/* Hover: translateY(-5px), shadow var(--sombra-lg) */
```

### Buttons
```css
background: var(--naranja-itau);
color: var(--blanco);
border-radius: 25px;
padding: 15px 25px;
border: none;
cursor: pointer;
transition: transform 0.2s, box-shadow 0.3s;
/* Hover: scale(1.05) */
/* Alt style: background var(--azul-medio) */
```

### Fixed Back Button
```css
position: fixed;
bottom: 20px;
right: 20px;
background: var(--azul-medio);
border-radius: 25px;
z-index: 1000;
/* Hover: background var(--naranja-itau), scale(1.05) */
```

## Responsive Breakpoints (Mobile-First)
- **Base (mobile):** < 768px — 1 column, hamburger menu
- **Tablet:** 768px — 2 columns
- **Desktop:** 1024px — 3-4 columns, full nav

## Spacing
- Section padding: 20px-40px
- Card gap: 20px
- Button padding: 10px 20px (small), 15px 25px (standard)
- Max content width: 1200px (centered)

## Authentication Roles
- **SuperAdmin:** Configured via .env only. Full access (dashboard, CMS, user management)
- **Supervisor:** Created by SuperAdmin. View content only. Tracked.
- **Asesor:** Created by SuperAdmin. View content only. Tracked.
- No self-registration.

## Naming Conventions
- Database: snake_case (page_views, click_events)
- Python: snake_case (get_user, create_content)
- URLs: kebab-case (/admin/contents, /api/track/pageview)
- Templates: snake_case (content_edit.html)
- CSS classes: kebab-case (.card-container, .search-bar)

## Important Rules
- All UI text in Spanish
- Copyright: "ArrowX"
- Always use CSS variables for colors, never hardcode hex values in new code
- Images stored in static/imagenes/
- All pages must include tracking.js for analytics
- Mobile-first: design for small screens, enhance for larger
