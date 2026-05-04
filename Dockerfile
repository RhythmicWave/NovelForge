# Stage 1: Build frontend
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --ignore-scripts
COPY frontend/ ./
RUN npx --yes cross-env VITE_APP_PLATFORM=web vite build -c vite.config.web.ts

# Stage 2: Runtime backend + static serve
FROM python:3.13-slim-bookworm
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./

# Copy built frontend
COPY --from=frontend-build /build/dist-web ./static

EXPOSE 54321
CMD ["python", "serve_web.py"]
