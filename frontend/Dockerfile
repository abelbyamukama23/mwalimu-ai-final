FROM node:20-alpine

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

# Install deps first for layer caching.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* are inlined at build time; Railway passes this service's
# NEXT_PUBLIC_PLATFORM_API_BASE_URL into the build environment.
RUN NEXT_PUBLIC_PLATFORM_API_BASE_URL=$NEXT_PUBLIC_PLATFORM_API_BASE_URL npm run build

EXPOSE 3000

CMD ["sh", "-c", "npx next start -p ${PORT:-3000}"]
