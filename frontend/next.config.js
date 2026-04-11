module.exports = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_USE_MOCK: process.env.NEXT_PUBLIC_USE_MOCK,
    AUTH0_BASE_URL: process.env.AUTH0_BASE_URL,
    AUTH0_ISSUER_BASE_URL: process.env.AUTH0_ISSUER_BASE_URL,
    AUTH0_AUDIENCE: process.env.AUTH0_AUDIENCE,
    NEXT_PUBLIC_GOOGLE_MAPS_API_KEY: process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY,
  },
};