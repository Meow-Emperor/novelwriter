// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { GlassCard } from '@/components/GlassCard'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { LegalPageFrame } from '@/components/legal/LegalPageFrame'
import { LEGAL_CONTACT_EMAIL, formatLegalLastUpdated, getLegalContactHref } from '@/content/legal'

const contactHref = getLegalContactHref()

function Section({ title, dateLabel, children }: { title: string; dateLabel: string; children: ReactNode }) {
  return (
    <GlassCard className="px-6 py-6 md:px-8 md:py-7">
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-mono text-xl font-semibold text-foreground md:text-2xl">{title}</h2>
          <span className="text-xs text-muted-foreground">{dateLabel}</span>
        </div>
        <div className="space-y-3 text-sm leading-7 text-muted-foreground md:text-[15px]">{children}</div>
      </div>
    </GlassCard>
  )
}

export default function Terms() {
  const { locale, t } = useUiLocale()
  const dateLabel = formatLegalLastUpdated(locale)
  const contactLabel = LEGAL_CONTACT_EMAIL || t('legal.contact.unconfigured')

  return (
    <LegalPageFrame
      eyebrow={t('terms.eyebrow')}
      title={t('terms.title')}
      summary={t('terms.summary')}
      headerNote={t('legal.lastUpdatedNote', { date: dateLabel })}
    >
      <Section title={t('terms.scope.title')} dateLabel={dateLabel}>
        <p>{t('terms.scope.body1')}</p>
        <p>{t('terms.scope.body2')}</p>
      </Section>

      <Section title={t('terms.service.title')} dateLabel={dateLabel}>
        <p>{t('terms.service.body1')}</p>
        <p>{t('terms.service.body2')}</p>
      </Section>

      <Section title={t('terms.upload.title')} dateLabel={dateLabel}>
        <ul className="list-disc space-y-2 pl-5">
          <li>{t('terms.upload.item1')}</li>
          <li>{t('terms.upload.item2')}</li>
          <li>{t('terms.upload.item3')}</li>
        </ul>
        <p>{t('terms.upload.body')}</p>
      </Section>

      <Section title={t('terms.prohibited.title')} dateLabel={dateLabel}>
        <ul className="list-disc space-y-2 pl-5">
          <li>{t('terms.prohibited.item1')}</li>
          <li>{t('terms.prohibited.item2')}</li>
          <li>{t('terms.prohibited.item3')}</li>
        </ul>
      </Section>

      <Section title={t('terms.ai.title')} dateLabel={dateLabel}>
        <p>{t('terms.ai.body1')}</p>
        <p>{t('terms.ai.body2')}</p>
      </Section>

      <Section title={t('terms.risk.title')} dateLabel={dateLabel}>
        <p>{t('terms.risk.body1')}</p>
        <p>{t('terms.risk.body2')}</p>
      </Section>

      <Section title={t('terms.related.title')} dateLabel={dateLabel}>
        <p>
          {t('terms.related.intro')}
          <Link to="/privacy" className="mx-1 text-foreground underline decoration-accent/60 underline-offset-4 transition-colors hover:text-accent">
            {t('footer.link.privacy')}
          </Link>
          {t('terms.related.and')}
          <Link to="/copyright" className="mx-1 text-foreground underline decoration-accent/60 underline-offset-4 transition-colors hover:text-accent">
            {t('footer.link.copyright')}
          </Link>
          {t('terms.related.outro')}
        </p>
        <p>
          {t('legal.contactLabel')}
          {contactHref ? (
            <a href={contactHref} className="text-foreground underline decoration-accent/60 underline-offset-4 transition-colors hover:text-accent">
              {contactLabel}
            </a>
          ) : (
            <span className="text-foreground">{contactLabel}</span>
          )}
        </p>
      </Section>
    </LegalPageFrame>
  )
}
