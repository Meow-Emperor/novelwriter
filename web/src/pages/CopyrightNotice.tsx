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

export default function CopyrightNotice() {
  const { locale, t } = useUiLocale()
  const dateLabel = formatLegalLastUpdated(locale)
  const contactLabel = LEGAL_CONTACT_EMAIL || t('legal.contact.unconfigured')

  return (
    <LegalPageFrame
      eyebrow={t('copyright.eyebrow')}
      title={t('copyright.title')}
      summary={t('copyright.summary')}
      headerNote={t('legal.lastUpdatedNote', { date: dateLabel })}
    >
      <Section title={t('copyright.scope.title')} dateLabel={dateLabel}>
        <p>{t('copyright.scope.body1')}</p>
        <p>{t('copyright.scope.body2')}</p>
      </Section>

      <Section title={t('copyright.submit.title')} dateLabel={dateLabel}>
        <p>{t('copyright.submit.body1')}</p>
        <ul className="list-disc space-y-2 pl-5">
          <li>{t('copyright.submit.item1')}</li>
          <li>{t('copyright.submit.item2')}</li>
          <li>{t('copyright.submit.item3')}</li>
          <li>{t('copyright.submit.item4')}</li>
        </ul>
      </Section>

      <Section title={t('copyright.action.title')} dateLabel={dateLabel}>
        <p>{t('copyright.action.body1')}</p>
        <p>{t('copyright.action.body2')}</p>
      </Section>

      <Section title={t('copyright.counter.title')} dateLabel={dateLabel}>
        <p>{t('copyright.counter.body1')}</p>
        <p>{t('copyright.counter.body2')}</p>
      </Section>

      <Section title={t('copyright.contact.title')} dateLabel={dateLabel}>
        <p>
          {t('legal.contactEmailLabel')}
          {contactHref ? (
            <a href={contactHref} className="text-foreground underline decoration-accent/60 underline-offset-4 transition-colors hover:text-accent">
              {contactLabel}
            </a>
          ) : (
            <span className="text-foreground">{contactLabel}</span>
          )}
        </p>
        {!contactHref ? (
          <p className="rounded-xl border border-dashed border-[var(--nw-glass-border-hover)] bg-white/5 px-4 py-3 text-foreground/80">
            {t('copyright.contact.missing')}
          </p>
        ) : null}
      </Section>
    </LegalPageFrame>
  )
}
