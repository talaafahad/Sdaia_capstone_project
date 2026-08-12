/**
 * Intake form field spec — implementation plan section 13, plus the
 * business-category map from section 10.
 *
 * Required fields block progression to the Regulation Agent. Optional fields
 * proceed without them but are flagged "readiness-limiting" when absent.
 */

import { z } from 'zod';

/** Keys of BUSINESS_CATEGORY_AGENCIES, implementation plan section 10. */
export const BUSINESS_CATEGORIES = [
  { value: 'food_beverage_fixed', label: 'Food & beverage — fixed premises' },
  { value: 'food_truck_mobile', label: 'Food truck / mobile cart' },
  { value: 'personal_care_spa', label: 'Personal care / spa' },
  { value: 'professional_office', label: 'Professional office' },
  { value: 'nonprofit_org', label: 'Non-profit organisation' },
] as const;

export const APPLICANT_STATUSES = [
  { value: 'saudi_national', label: 'Saudi national' },
  { value: 'gcc_national', label: 'GCC national' },
  { value: 'non_gcc_resident', label: 'Non-GCC resident' },
] as const;

/**
 * Section 13: "Scope to cities you've actually built a corpus for (Riyadh at
 * minimum)." `data/gov_corpus/` is empty until Phase 0, so only Riyadh is
 * selectable; the rest are listed but disabled so the scoping is visible
 * rather than silently absent.
 */
export const CITIES = [
  { value: 'riyadh', label: 'Riyadh', corpusReady: true },
  { value: 'jeddah', label: 'Jeddah', corpusReady: false },
  { value: 'dammam', label: 'Dammam', corpusReady: false },
  { value: 'makkah', label: 'Makkah', corpusReady: false },
] as const;

const CATEGORY_VALUES = BUSINESS_CATEGORIES.map((c) => c.value);
const STATUS_VALUES = APPLICANT_STATUSES.map((s) => s.value);
const READY_CITY_VALUES = CITIES.filter((c) => c.corpusReady).map((c) => c.value);

/** Blank number inputs arrive as '' — coerce to undefined so `required` fires. */
const toNumber = (v: unknown): number | undefined => {
  if (v === '' || v === null || v === undefined) return undefined;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : undefined;
};

const requiredNumber = (label: string) =>
  z.preprocess(
    toNumber,
    z
      .number({ message: `${label} is required` })
      .positive({ message: `${label} must be greater than zero` })
  );

const optionalNumber = (label: string) =>
  z.preprocess(
    toNumber,
    z
      .number()
      .nonnegative({ message: `${label} cannot be negative` })
      .optional()
  );

export const intakeSchema = z.object({
  // ---- Required (section 13) ----
  goal: z
    .string()
    .trim()
    .min(15, { message: 'Describe your goal in a full sentence (at least 15 characters).' }),
  business_category: z.enum(CATEGORY_VALUES as [string, ...string[]], {
    message: 'Select a business category.',
  }),
  city: z.enum(READY_CITY_VALUES as [string, ...string[]], {
    message: 'Select a city with a built regulation corpus.',
  }),
  district: z.string().trim().min(2, { message: 'District is required.' }),
  // Section 13 is explicit: do NOT default this silently — an unselected value
  // must block progression rather than assume "Saudi national".
  applicant_status: z.enum(STATUS_VALUES as [string, ...string[]], {
    message: 'Applicant status is required — this determines the registration pathway.',
  }),
  area_sqm_stated: requiredNumber('Estimated area'),
  expected_annual_revenue_sar: requiredNumber('Expected annual revenue'),

  // ---- Optional (section 13) — readiness-limiting when absent ----
  budget_sar: optionalNumber('Budget'),
  employee_count: optionalNumber('Number of employees'),
  target_opening_date: z.string().optional(),
  applicant_age: optionalNumber('Applicant age'),
});

export type IntakeFormValues = z.input<typeof intakeSchema>;
export type IntakeValues = z.output<typeof intakeSchema>;

/** Fields that, when blank, cap achievable readiness (section 13). */
export const READINESS_LIMITING_FIELDS: {
  key: keyof IntakeValues;
  label: string;
  why: string;
}[] = [
  { key: 'budget_sar', label: 'Budget (SAR)', why: 'Fee estimate falls back to AI estimates only' },
  { key: 'employee_count', label: 'Number of employees', why: 'GOSI / Qiwa / WPS branches stay unevaluated' },
  { key: 'target_opening_date', label: 'Target opening date', why: 'Roadmap artifact has no timeline' },
];

/**
 * Implementation plan section 10: do not build a minor-applicant pathway.
 * Detect the case, decline to proceed, and point at an official source rather
 * than fabricating a process.
 */
export const MINOR_APPLICANT_NOTICE =
  'Commercial registration for applicants under 18 requires guardian involvement. ' +
  'GovFlow does not model this pathway — consult the Saudi Business Center ' +
  '(business.sa) directly before proceeding.';

export const isMinorApplicant = (age: number | undefined): boolean =>
  age !== undefined && age < 18;
