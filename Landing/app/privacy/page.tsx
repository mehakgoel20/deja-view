import type { Metadata } from "next";
import { LegalPage, LegalSection, Missing } from "@/components/legal-page";
import { site } from "@/lib/site";

// LEGAL REVIEW REQUIRED: this text was not written or checked by a lawyer.
// Have it reviewed, and fill in the missing details in lib/site.ts, before launch.

export const metadata: Metadata = {
  title: "Privacy policy",
  description: `What personal data ${site.name} handles, who processes it and how to have it removed.`,
};

export default function PrivacyPage() {
  const { owner, email, address } = site.legal;

  return (
    <LegalPage title="Privacy policy">
      <LegalSection heading="Who is responsible">
        <p>
          {site.name} is operated by {owner}, an individual. In this policy, &quot;we&quot; means {owner}.
        </p>
        <p>
          Contact email: <a href={`mailto:${email}`}>{email}</a>
        </p>
        <p>{address ? `Postal address: ${address}` : <Missing what="Postal address" />}</p>
      </LegalSection>

      <LegalSection heading="What we collect">
        <ul>
          <li>
            <strong>Account details.</strong> When you sign up we receive your email address and, if you provide
            them, your name and profile picture. If you sign in with another provider such as Google, we receive
            the identifier of that account.
          </li>
          <li>
            <strong>Session details.</strong> Each sign-in records the time, your IP address and your browser and
            device type. A cookie keeps you signed in.
          </li>
          <li>
            <strong>Issue descriptions.</strong> The text you submit for analysis is sent to the analysis service
            and on to OpenAI, which produces the answer. The analysis service does not keep a copy.
          </li>
          <li>
            <strong>Recent analyses.</strong> The last 10 analyses are stored in your own browser. They are not sent
            to us.
          </li>
        </ul>
        <p>This site has no advertising or analytics trackers.</p>
      </LegalSection>

      <LegalSection heading="Clerk, our sign-in provider">
        <p>
          Accounts and sign-in are handled by Clerk, Inc. Clerk stores your account details, your password in
          hashed form if you set one, the identifiers of any connected sign-in providers, and your session details.
          We can see your account and session details in the Clerk dashboard. We cannot see your password.
        </p>
        <p>
          See the <a href="https://clerk.com/legal/privacy">Clerk privacy policy</a>.
        </p>
      </LegalSection>

      <LegalSection heading="OpenAI">
        <p>
          Issue descriptions are processed by OpenAI to find similar past incidents and to write the answer. Do not
          include passwords, access keys or personal data about other people in a description.
        </p>
        <p>
          See the <a href="https://openai.com/policies/privacy-policy">OpenAI privacy policy</a>.
        </p>
      </LegalSection>

      <LegalSection heading="Why we use this data">
        <ul>
          <li>To create your account and keep it secure.</li>
          <li>To produce the analysis you ask for.</li>
          <li>To reply when you contact us.</li>
        </ul>
        <p>We do not sell personal data.</p>
      </LegalSection>

      <LegalSection heading="How long we keep it">
        <p>
          Account and session details are kept until your account is deleted. Analyses stored in your browser stay
          there until you press Clear in the analysis app or clear your browser storage.
        </p>
      </LegalSection>

      <LegalSection heading="Your choices">
        <p>
          You can ask for a copy of your account data, ask us to correct it, or ask us to delete your account. Email{" "}
          <a href={`mailto:${email}`}>{email}</a>. Depending on where you live, the law may give you further
          rights over your data.
        </p>
      </LegalSection>

      <LegalSection heading="Changes to this policy">
        <p>If this policy changes, the new version is published on this page with a new date at the top.</p>
      </LegalSection>
    </LegalPage>
  );
}
