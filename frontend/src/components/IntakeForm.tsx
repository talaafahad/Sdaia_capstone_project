import { Upload, ChevronDown } from 'lucide-react'
import type { FormValues } from '../types/bosalah'

const BUSINESS_CATEGORIES = [
  'Food & Beverage', 'Retail', 'Professional Services', 'Health & Wellness',
  'Education & Training', 'Technology & IT', 'Construction & Real Estate',
  'Tourism & Hospitality', 'Transportation & Logistics', 'Manufacturing', 'Other',
]

const CITIES = [
  'Riyadh', 'Jeddah', 'Dammam', 'Mecca', 'Medina',
  'Khobar', 'Tabuk', 'Abha', 'Khamis Mushait', 'Hail',
]

// ─── Sub-components ───────────────────────────────────────────────────────────

function Label({ text, required, htmlFor }: { text: string; required?: boolean; htmlFor: string }) {
  return (
    <label
      htmlFor={htmlFor}
      className="block text-sm font-medium mb-2"
      style={{ color: '#D4D4D4' }}
    >
      {text}
      {required && (
        <span style={{ color: '#C0564B', marginLeft: 2 }} aria-hidden>*</span>
      )}
    </label>
  )
}

function Input({ id, type = 'text', placeholder, value, onChange, min, max, style: extraStyle }: {
  id: string; type?: string; placeholder?: string; value: string
  onChange: (v: string) => void; min?: number; max?: number; style?: React.CSSProperties
}) {
  return (
    <input
      id={id} type={type} min={min} max={max} placeholder={placeholder} value={value}
      onChange={e => onChange(e.target.value)}
      className="field-input"
      style={extraStyle}
    />
  )
}

function Select({ id, value, onChange, options, placeholder }: {
  id: string; value: string; onChange: (v: string) => void
  options: string[]; placeholder: string
}) {
  return (
    <div className="relative">
      <select
        id={id} value={value} onChange={e => onChange(e.target.value)}
        className="field-input appearance-none pr-10 cursor-pointer"
        style={{ color: value === '' ? 'var(--color-text-faint)' : 'var(--color-text-primary)' }}
      >
        <option value="" disabled>{placeholder}</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
      <ChevronDown
        size={14}
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2"
        style={{ color: '#616161' }}
      />
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

interface IntakeFormProps {
  values: FormValues
  onChange: (field: keyof FormValues, value: string) => void
  onSubmit: (values: FormValues) => void
  onFileChange: (file: File | null) => void
}

export default function IntakeForm({ values, onChange, onSubmit, onFileChange }: IntakeFormProps) {
  const complete =
    values.businessGoal.trim() !== '' &&
    values.businessCategory !== '' &&
    values.city !== '' &&
    values.district.trim() !== '' &&
    values.applicantStatus !== '' &&
    values.areaSqm.trim() !== '' &&
    values.annualRevenueSAR.trim() !== ''

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (complete) onSubmit(values)
  }

  const filledCount = [
    values.businessGoal, values.businessCategory, values.city,
    values.district, values.applicantStatus, values.areaSqm, values.annualRevenueSAR,
  ].filter(v => v.trim() !== '').length

  const progressPct = Math.round((filledCount / 7) * 100)

  return (
    <section id="intake" className="py-16 px-0">
      {/* Header */}
      <div className="mb-10 animate-fade-up">
        <p className="section-label mb-4">Case details</p>
        <h2
          className="font-extrabold tracking-tight mb-2"
          style={{ fontSize: 'clamp(24px, 4vw, 36px)', color: '#F1F1F1' }}
        >
          Tell us about your case
        </h2>
        <p className="text-sm" style={{ color: '#B0B0B0' }}>
          Fields marked <span style={{ color: '#C0564B', fontWeight: 600 }}>*</span> are required.
        </p>
      </div>

      {/* Completion mini-bar */}
      <div className="mb-8 animate-fade-up-1">
        <div className="flex justify-between text-xs mb-1.5" style={{ color: '#616161' }}>
          <span>{filledCount} of 7 required fields</span>
          <span style={{ color: complete ? '#5BCD84' : '#9D7CFF' }}>
            {complete ? '✓ Ready to submit' : `${progressPct}%`}
          </span>
        </div>
        <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(129,116,201,0.15)' }}>
          <div
            className="h-full rounded-full transition-[width] duration-500 ease-out"
            style={{
              width: `${progressPct}%`,
              background: complete
                ? 'linear-gradient(to right, #5BCD84, #93DEAE)'
                : 'linear-gradient(to right, #8174C9, #9D7CFF)',
            }}
          />
        </div>
      </div>

      <form onSubmit={handleSubmit} noValidate>
        {/* ── REQUIRED ── */}
        <div
          className="rounded-2xl p-6 mb-6 animate-fade-up-1"
          style={{
            background: 'rgba(23,27,61,0.7)',
            border: '1px solid rgba(129,116,201,0.18)',
          }}
        >
          <p className="section-label mb-6">Required</p>

          {/* Business goal — full width */}
          <div className="mb-5">
            <Label text="Business goal" required htmlFor="businessGoal" />
            <textarea
              id="businessGoal" rows={3}
              placeholder="e.g. I want to open a specialty coffee shop in Al-Olaya, Riyadh."
              value={values.businessGoal}
              onChange={e => onChange('businessGoal', e.target.value)}
              className="field-input resize-none"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <Label text="Business category" required htmlFor="businessCategory" />
              <Select
                id="businessCategory" value={values.businessCategory}
                onChange={v => onChange('businessCategory', v)}
                options={BUSINESS_CATEGORIES} placeholder="Select a category…"
              />
            </div>
            <div>
              <Label text="City" required htmlFor="city" />
              <Select
                id="city" value={values.city}
                onChange={v => onChange('city', v)}
                options={CITIES} placeholder="Select a city…"
              />
            </div>
            <div>
              <Label text="District" required htmlFor="district" />
              <Input id="district" placeholder="e.g. Al-Olaya" value={values.district} onChange={v => onChange('district', v)} />
            </div>
            <div>
              <Label text="Applicant status" required htmlFor="applicantStatus" />
              <div className="relative">
                <select
                  id="applicantStatus" value={values.applicantStatus}
                  onChange={e => onChange('applicantStatus', e.target.value)}
                  className="field-input appearance-none pr-10 cursor-pointer"
                  style={{ color: values.applicantStatus === '' ? 'var(--color-text-faint)' : 'var(--color-text-primary)' }}
                >
                  <option value="" disabled>Select status…</option>
                  <option value="saudi">Saudi national</option>
                  <option value="gcc">GCC national</option>
                  <option value="non_gcc">Non-GCC resident</option>
                </select>
                <ChevronDown size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2" style={{ color: '#616161' }} />
              </div>
            </div>
            <div>
              <Label text="Estimated area (sqm)" required htmlFor="areaSqm" />
              <Input id="areaSqm" type="number" min={1} placeholder="e.g. 120" value={values.areaSqm} onChange={v => onChange('areaSqm', v)} />
            </div>
            <div>
              <Label text="Expected annual revenue (SAR)" required htmlFor="annualRevenueSAR" />
              <Input id="annualRevenueSAR" type="number" min={0} placeholder="e.g. 500000" value={values.annualRevenueSAR} onChange={v => onChange('annualRevenueSAR', v)} />
            </div>
          </div>
        </div>

        {/* ── OPTIONAL ── */}
        <div
          className="rounded-2xl p-6 mb-6 animate-fade-up-2"
          style={{
            background: 'rgba(23,27,61,0.5)',
            border: '1px solid rgba(129,116,201,0.1)',
          }}
        >
          <p className="section-label mb-6">Optional</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <Label text="Budget (SAR)" htmlFor="budgetSAR" />
              <Input id="budgetSAR" type="number" min={0} placeholder="e.g. 200000" value={values.budgetSAR} onChange={v => onChange('budgetSAR', v)} />
            </div>
            <div>
              <Label text="Number of employees" htmlFor="numberOfEmployees" />
              <Input id="numberOfEmployees" type="number" min={0} placeholder="e.g. 5" value={values.numberOfEmployees} onChange={v => onChange('numberOfEmployees', v)} />
            </div>
            <div>
              <Label text="Target opening date" htmlFor="targetOpeningDate" />
              <Input id="targetOpeningDate" type="date" value={values.targetOpeningDate} onChange={v => onChange('targetOpeningDate', v)} style={{ colorScheme: 'dark' }} />
            </div>
            <div>
              <Label text="Applicant age" htmlFor="applicantAge" />
              <Input id="applicantAge" type="number" min={0} max={120} placeholder="e.g. 28" value={values.applicantAge} onChange={v => onChange('applicantAge', v)} />
              <p className="mt-1.5 text-xs" style={{ color: '#616161' }}>Only used to detect the under-18 case.</p>
            </div>
          </div>

          {/* Document upload */}
          <div className="mt-5">
            <Label text="Supporting document" htmlFor="documentUpload" />
            <label
              htmlFor="documentUpload"
              className="relative flex items-center gap-4 rounded-xl p-5 cursor-pointer transition-all duration-200"
              style={{
                background: 'rgba(16,18,43,0.6)',
                border: '1.5px dashed rgba(129,116,201,0.3)',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(157,124,255,0.5)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(129,116,201,0.3)' }}
            >
              <div
                className="flex items-center justify-center rounded-xl shrink-0"
                style={{ width: 44, height: 44, background: 'rgba(129,116,201,0.1)', border: '1px solid rgba(129,116,201,0.2)' }}
              >
                <Upload size={18} style={{ color: '#9D7CFF' }} />
              </div>
              <div>
                <p className="text-sm font-medium" style={{ color: '#F1F1F1' }}>Upload a lease agreement or supporting document</p>
                <p className="text-xs mt-0.5" style={{ color: '#616161' }}>PDF or TXT · Max 10 MB</p>
              </div>
              <input
                id="documentUpload" type="file" accept=".pdf,.txt"
                onChange={e => onFileChange(e.target.files?.[0] ?? null)}
                className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
              />
            </label>
          </div>
        </div>

        {/* ── Submit bar ── */}
        <div
          className="sticky bottom-6 z-10 flex items-center justify-between gap-4 rounded-2xl px-5 py-4 animate-fade-up-3"
          style={{
            background: 'rgba(23,27,61,0.95)',
            border: '1px solid rgba(129,116,201,0.25)',
            backdropFilter: 'blur(12px)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          }}
        >
          <div>
            {complete ? (
              <p className="text-sm font-medium" style={{ color: '#5BCD84' }}>✓ All required fields complete</p>
            ) : (
              <p className="text-sm" style={{ color: '#616161' }}>Complete all required fields to continue</p>
            )}
          </div>
          <button
            type="submit"
            disabled={!complete}
            className="px-8 py-3 rounded-xl font-semibold text-sm text-white transition-all duration-200 shrink-0"
            style={{
              background: complete
                ? 'linear-gradient(135deg, #8174C9, #9D7CFF)'
                : 'rgba(129,116,201,0.25)',
              boxShadow: complete ? '0 4px 16px rgba(157,124,255,0.35)' : 'none',
              cursor: complete ? 'pointer' : 'not-allowed',
              color: complete ? 'white' : '#616161',
            }}
            onMouseEnter={e => { if (complete) { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = '0 8px 24px rgba(157,124,255,0.5)' } }}
            onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = complete ? '0 4px 16px rgba(157,124,255,0.35)' : 'none' }}
          >
            Analyse My Case →
          </button>
        </div>
      </form>
    </section>
  )
}
