import type { NextConfig } from "next";

// Production is a static export served by the gateway (nginx), which also proxies /v1, /ws and
// /static to Django, so the browser only ever talks to one origin. `next dev` proxies /v1 itself.
const isDev = process.env.NODE_ENV === "development";
const apiProxy = process.env.API_PROXY ?? "http://localhost:8001";

const config: NextConfig = {
  output: isDev ? undefined : "export",
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
  ...(isDev && {
    skipTrailingSlashRedirect: true,
    async rewrites() {
      return [{ source: "/v1/:path*", destination: `${apiProxy}/v1/:path*` }];
    },
  }),
};

export default config;
