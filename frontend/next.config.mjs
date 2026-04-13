/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  // Internal Flask backend URL used only in server-side code
  // The Next.js proxy route (/api/flask/[...path]) forwards requests here
  env: {
    FLASK_INTERNAL_URL: process.env.FLASK_INTERNAL_URL ?? 'http://localhost:5102',
  },
};

export default nextConfig;
