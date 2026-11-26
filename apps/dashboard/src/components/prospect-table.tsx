import Link from "next/link";

import { Badge } from "@/components/badge";
import { formatDate } from "@/components/ui";
import type { Prospect } from "@/lib/discovery";

export function ProspectTable({ items }: { items: Prospect[] }) {
  if (!items.length) return <p className="text-sm text-muted">No prospects yet.</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[44rem] text-sm">
        <caption className="sr-only">Prospects</caption>
        <thead className="text-left text-muted">
          <tr>
            <th scope="col" className="px-4 py-3 font-medium">
              Business (as its website states)
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Website
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              State
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Qualification
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Verified
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <tr key={p.id} className="border-t border-line">
              <td className="px-4 py-3">
                <Link href={`/prospects/${p.id}`} className="font-medium text-accent hover:underline">
                  {p.business_name}
                </Link>
                {p.do_not_contact && (
                  <span className="ml-2">
                    <Badge value="DO_NOT_CONTACT" label="do not contact" />
                  </span>
                )}
              </td>
              <td className="px-4 py-3 break-all text-muted">
                {p.verified_domain}
                {p.branch_key}
              </td>
              <td className="px-4 py-3">
                <Badge value={p.state} />
              </td>
              <td className="px-4 py-3">
                {p.qualification_band ? <Badge value={p.qualification_band} /> : "—"}
                {p.qualification_score !== null && (
                  <span className="ml-2 tabular-nums text-muted">
                    {Number(p.qualification_score).toFixed(0)}
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-muted">{formatDate(p.last_verified_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
