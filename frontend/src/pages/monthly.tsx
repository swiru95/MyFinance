import { useEffect } from "react";
import { useRouter } from "next/router";

/** /monthly retired: spending and its analytics live under /expenses#monthly
 *  now, other income under /income. This keeps old links and bookmarks
 *  working instead of 404ing them. */
export default function MonthlyRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/expenses#monthly");
  }, [router]);

  return null;
}
