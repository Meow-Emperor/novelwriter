// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import type { ReactNode } from 'react'
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

export default function Privacy() {
  const { locale, t } = useUiLocale()
  const dateLabel = formatLegalLastUpdated(locale)
  const contactLabel = LEGAL_CONTACT_EMAIL || t('legal.contact.unconfigured')

  return (
    <LegalPageFrame
      eyebrow={t('privacy.eyebrow')}
      title={t('privacy.title')}
      summary={t('privacy.summary')}
      headerNote={t('legal.lastUpdatedNote', { date: dateLabel })}
    >
      <Section title={t('privacy.scope.title')} dateLabel={dateLabel}>
        <p>{t('privacy.scope.body1')}</p>
        <p>{t('privacy.scope.body2')}</p>
      </Section>

      <Section title={t('privacy.info.title')} dateLabel={dateLabel}>
        <ul className="list-disc space-y-2 pl-5">
          <li>{t('privacy.info.item1')}</li>
          <li>{t('privacy.info.item2')}</li>
          <li>{t('privacy.info.item3')}</li>
        </ul>
      </Section>

      <Section title={t('privacy.purpose.title')} dateLabel={dateLabel}>
        <p>{t('privacy.purpose.body1')}</p>
        <p>{t('privacy.purpose.body2')}</p>
      </Section>

      <Section title={t('privacy.model.title')} dateLabel={dateLabel}>
        <p>{t('privacy.model.body1')}</p>
        <p>{t('privacy.model.body2')}</p>
      </Section>

      <Section title={t('privacy.retention.title')} dateLabel={dateLabel}>
        <p>{t('privacy.retention.body1')}</p>
        <p>{t('privacy.retention.body2')}</p>
      </Section>

      <Section title={t('privacy.choice.title')} dateLabel={dateLabel}>
        <p>{t('privacy.choice.body1')}</p>
        <p>
          {t('privacy.choice.body2')}
          {contactHref ? (
            <a href={contactHref} className="ml-1 text-foreground underline decoration-accent/60 underline-offset-4 transition-colors hover:text-accent">
              {contactLabel}
            </a>
          ) : (
            <span className="ml-1 text-foreground">{contactLabel}</span>
          )}
        </p>
      </Section>
    </LegalPageFrame>
  )
}
