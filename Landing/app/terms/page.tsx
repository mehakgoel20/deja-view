import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage, LegalSection, Missing } from "@/components/legal-page";
import { site } from "@/lib/site";

// LEGAL REVIEW REQUIRED: this text was not written or checked by a lawyer.
// Have it reviewed, and fill in the missing details in lib/site.ts, before launch.

export const metadata: Metadata = {
  title: "Terms of use",
  description: `The terms that apply when you use ${site.name}.`,
};

export default function TermsPage() {
  const { owner, email, address, jurisdiction } = site.legal;

  return (
    <LegalPage title="Terms of use">
      <LegalSection heading="Who these terms are with">
        <p>
          {site.name} is operated by {owner}, an individual. By creating an account or using the service you agree
          to these terms.
        </p>
        <p>
          Contact email: <a href={`mailto:${email}`}>{email}</a>
        </p>
        <p>{address ? `Postal address: ${address}` : <Missing what="Postal address" />}</p>
      </LegalSection>

      <LegalSection heading="What the service does">
        <p>
          You describe a production issue. The service compares it with a collection of past production incidents and uses a
          language model to suggest likely root causes and fixes.
        </p>
        <p>
          <strong>The output is a suggestion, not a diagnosis.</strong> It can be wrong or incomplete, and the
          confidence figure is reported by the model itself. Check every suggestion before you change a production
          system. You are responsible for the changes you make.
        </p>
      </LegalSection>

      <LegalSection heading="Your account">
        <p>
          You need an account to use the dashboard. Keep your sign-in details private and tell us if you think
          someone else has used your account. You are responsible for what happens under it.
        </p>
      </LegalSection>

      <LegalSection heading="Acceptable use">
        <ul>
          <li>Do not use the service to break the law.</li>
          <li>Do not try to disrupt it or to reach data that is not yours.</li>
          <li>
            Do not submit passwords, access keys, or information you are not allowed to share. Descriptions are sent
            to a third party for processing, as the <Link href="/privacy">privacy policy</Link> explains.
          </li>
        </ul>
      </LegalSection>

      <LegalSection heading="Your content">
        <p>
          The issue descriptions you submit remain yours. You allow us to process them, and to pass them to our
          processors, only as far as needed to return an answer.
        </p>
      </LegalSection>

      <LegalSection heading="Availability and warranty">
        <p>
          The service is provided as it is. We may change it, limit it or stop offering it. To the extent the law
          allows, we give no warranty that it will be available, free of errors or fit for a particular purpose.
        </p>
      </LegalSection>

      <LegalSection heading="Liability">
        <p>
          To the extent the law allows, we are not liable for indirect or consequential loss, or for loss that
          results when you act on a suggestion. Nothing in these terms limits liability that cannot be limited by
          law.
        </p>
      </LegalSection>

      <LegalSection heading="Ending your use">
        <p>
          You can stop using the service at any time and ask us to delete your account. We may suspend an account
          that breaks these terms.
        </p>
      </LegalSection>

      <LegalSection heading="Governing law">
        <p>
          {jurisdiction ? (
            `These terms are governed by the laws of ${jurisdiction}.`
          ) : (
            <Missing what="Governing country or state" />
          )}
        </p>
      </LegalSection>

      <LegalSection heading="Changes to these terms">
        <p>If these terms change, the new version is published on this page with a new date at the top.</p>
      </LegalSection>
    </LegalPage>
  );
}
