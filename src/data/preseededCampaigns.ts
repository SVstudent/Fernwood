import { Campaign } from '../types';
import { generateCampaignSVG } from '../utils/svgGenerators';

export const PRESEEDED_CAMPAIGNS: Campaign[] = [
  {
    id: 'camp-fernwood-goods',
    brandName: 'Fernwood Goods',
    productService: 'Handcrafted Heritage Leather Bags & Sustainable Canvas Goods',
    targetAudience: 'Eco-conscious design lovers, weekend travelers, urban professionals',
    briefText: 'Highlight sustainable craftsmanship, warmth of forest oak leather, and lifetime durability. Tone should feel warm, grounded, and rustic yet refined.',
    toneTags: ['Earthy & Organic', 'Cozy & Warm'],
    colors: {
      primary: '#1E3A2B',
      secondary: '#F4F1EA',
      accent: '#D97706'
    },
    createdAt: '2026-07-28T14:22:00Z',
    updatedAt: '2026-07-28T14:24:15Z',
    status: 'completed',
    overallQualityScore: 94,
    totalAttemptsCount: 4,
    retryCount: 1,
    assets: {
      image: {
        id: 'asset-img-1',
        campaignId: 'camp-fernwood-goods',
        type: 'image',
        status: 'passed',
        finalApprovedAttemptId: 'att-img-2',
        attempts: [
          {
            id: 'att-img-1',
            attemptNumber: 1,
            providerName: 'Genblaze Visual Engine',
            modelName: 'genblaze-image-v3',
            promptUsed: 'High-end product shot of leather backpack on sleek polished glass, studio lighting, cold blue tones.',
            timestamp: '2026-07-28T14:22:05Z',
            critiqueVerdict: 'FAIL',
            critique: {
              passed: false,
              overallScore: 62,
              reasoning: 'The generated image uses overly cold studio glass lighting that contradicts the requested "earthy, grounded, warm forest oak" mood.',
              suggestedFixes: 'Incorporate natural sunlight streaming through pine foliage, warm leather textures, and organic wood backgrounds.',
              criteria: [
                { name: 'Brand Tone Match', score: 55, targetScore: 85, passed: false, feedback: 'Too cold and sterile for an organic brand.' },
                { name: 'Visual Composition', score: 88, targetScore: 80, passed: true, feedback: 'Sharp detail and strong focal alignment.' },
                { name: 'Color Palette Alignment', score: 45, targetScore: 80, passed: false, feedback: 'Lacks warm amber or forest green accents.' }
              ]
            },
            content: {
              imageUrl: generateCampaignSVG({
                brandName: 'Fernwood Goods',
                tagline: 'Handcrafted Heritage',
                tone: 'Earthy & Organic',
                primaryColor: '#2B3A4A',
                secondaryColor: '#E2E8F0',
                accentColor: '#38BDF8',
                attemptNumber: 1
              }),
              aspectRatio: '16:9',
              primaryColor: '#2B3A4A',
              secondaryColor: '#E2E8F0'
            }
          },
          {
            id: 'att-img-2',
            attemptNumber: 2,
            providerName: 'Genblaze Visual Engine',
            modelName: 'genblaze-image-v3',
            promptUsed: 'REFINED: Handcrafted heritage leather weekender resting on mossy forest log, bathed in golden hour amber sunlight, deep pine green backdrop, rustic organic texture.',
            timestamp: '2026-07-28T14:22:25Z',
            critiqueVerdict: 'PASS',
            critique: {
              passed: true,
              overallScore: 96,
              reasoning: 'Exceptional warmth and texture alignment. Golden hour backlight accentuates the deep forest green and oak grain perfectly.',
              suggestedFixes: 'None. Approved for campaign kit.',
              criteria: [
                { name: 'Brand Tone Match', score: 98, targetScore: 85, passed: true, feedback: 'Perfect match for Earthy & Cozy mood.' },
                { name: 'Visual Composition', score: 94, targetScore: 80, passed: true, feedback: 'Balanced depth of field with golden light.' },
                { name: 'Color Palette Alignment', score: 96, targetScore: 80, passed: true, feedback: 'Accurately reflects #1E3A2B forest green and #D97706 warm amber.' }
              ]
            },
            content: {
              imageUrl: generateCampaignSVG({
                brandName: 'Fernwood Goods',
                tagline: 'Handcrafted Heritage for the Journey Ahead',
                tone: 'Earthy & Organic',
                primaryColor: '#1E3A2B',
                secondaryColor: '#F4F1EA',
                accentColor: '#D97706',
                attemptNumber: 2
              }),
              aspectRatio: '16:9',
              primaryColor: '#1E3A2B',
              secondaryColor: '#F4F1EA',
              accentColor: '#D97706'
            }
          }
        ]
      },
      audio: {
        id: 'asset-aud-1',
        campaignId: 'camp-fernwood-goods',
        type: 'audio',
        status: 'passed',
        finalApprovedAttemptId: 'att-aud-1',
        attempts: [
          {
            id: 'att-aud-1',
            attemptNumber: 1,
            providerName: 'Genblaze Voice Synthesis',
            modelName: 'genblaze-tts-pro',
            promptUsed: 'Voiceover: Resonant, calm, warm baritone. Pace: Measured and unhurried. Background: Subtle wind through pine trees acoustic guitar strum.',
            timestamp: '2026-07-28T14:23:00Z',
            critiqueVerdict: 'PASS',
            critique: {
              passed: true,
              overallScore: 92,
              reasoning: 'Voice modulation carries genuine authenticity and warmth without feeling dramatic or over-commercialized.',
              suggestedFixes: 'None.',
              criteria: [
                { name: 'Vocal Warmth', score: 94, targetScore: 85, passed: true, feedback: 'Resonant tone with gentle acoustic ambiance.' },
                { name: 'Pacing & Clarity', score: 90, targetScore: 80, passed: true, feedback: 'Crisp enunciation at 130 WPM.' }
              ]
            },
            content: {
              audioScript: 'Crafted from full-grain oak leather and stitched for a lifetime of stories. Fernwood Goods — Carry what matters.',
              audioVoice: 'Warm Forest Baritone',
              durationSeconds: 9.4,
              audioWaveformData: [20, 35, 60, 85, 40, 70, 95, 30, 50, 75, 45, 80, 60, 35, 20]
            }
          }
        ]
      },
      copy: {
        id: 'asset-cpy-1',
        campaignId: 'camp-fernwood-goods',
        type: 'copy',
        status: 'passed',
        finalApprovedAttemptId: 'att-cpy-1',
        attempts: [
          {
            id: 'att-cpy-1',
            attemptNumber: 1,
            providerName: 'Genblaze Copy LLM',
            modelName: 'gemini-2.5-pro',
            promptUsed: 'Generate brand campaign copywriting suite for Fernwood Goods emphasizing sustainable leather craftsmanship, timeless journey, and heirloom quality.',
            timestamp: '2026-07-28T14:23:40Z',
            critiqueVerdict: 'PASS',
            critique: {
              passed: true,
              overallScore: 95,
              reasoning: 'Evotive, evocative language that avoids generic hype verbs while building strong emotional resonance.',
              suggestedFixes: 'None.',
              criteria: [
                { name: 'Brand Tone Alignment', score: 96, targetScore: 85, passed: true, feedback: 'Rich storytelling voice.' },
                { name: 'Actionability', score: 94, targetScore: 80, passed: true, feedback: 'Clear call to explore the heirloom collection.' }
              ]
            },
            content: {
              headline: 'Made to Outlast the Horizon',
              subheadline: 'Handcrafted Heritage Bags & Canvas Goods Built for a Lifetime',
              bodyText: 'At Fernwood, we believe true luxury isn’t disposable. Every stitch is placed by hand using vegetable-tanned leather and heavy-duty organic canvas. Designed to age with grace and carry every milestone along your path.',
              callToAction: 'Explore the Heirloom Collection',
              keyBenefitBullets: [
                '100% Vegetable-tanned oak leather from ethical tanneries',
                'Hand-stitched brass hardware with lifetime repair guarantee',
                'Water-resistant organic wax canvas shell'
              ],
              socialPosts: [
                '🌲 Some things get better with every mile. Meets the Fernwood Heritage Weekender — built for those who value craftsmanship over quick trends. #FernwoodGoods #Handcrafted #MadeToLast',
                'Unbox a companion for life. Every crease tells your story. Discover our rustic canvas & leather series now. 🎒✨ #SlowFashion #HeritageGoods'
              ]
            }
          }
        ]
      }
    }
  },
  {
    id: 'camp-aeropulse',
    brandName: 'AeroPulse',
    productService: 'Spatial Audio Noise-Canceling Wireless Headphones',
    targetAudience: 'Audiophiles, commuters, remote creators, gamers',
    briefText: 'Ultra-sleek futuristic headphone campaign highlighting 40-hour acoustic bliss, active spatial isolation, and featherlight titanium architecture.',
    toneTags: ['High-Tech Futuristic', 'Minimalist Luxury'],
    colors: {
      primary: '#0F172A',
      secondary: '#38BDF8',
      accent: '#818CF8'
    },
    createdAt: '2026-07-29T10:15:00Z',
    updatedAt: '2026-07-29T10:18:10Z',
    status: 'completed',
    overallQualityScore: 91,
    totalAttemptsCount: 5,
    retryCount: 2,
    assets: {
      image: {
        id: 'asset-img-2',
        campaignId: 'camp-aeropulse',
        type: 'image',
        status: 'passed',
        finalApprovedAttemptId: 'att-img-aeropulse-3',
        attempts: [
          {
            id: 'att-img-aeropulse-1',
            attemptNumber: 1,
            providerName: 'Genblaze Visual Engine',
            modelName: 'genblaze-image-v3',
            promptUsed: 'Over-ear headphones floating in bright pastel pink studio background with flowers.',
            timestamp: '2026-07-29T10:15:10Z',
            critiqueVerdict: 'FAIL',
            critique: {
              passed: false,
              overallScore: 48,
              reasoning: 'Pastel flowers and bright pink background violate the high-tech titanium and spatial audio aesthetic requested in the brief.',
              suggestedFixes: 'Shift palette to midnight blue, cyan laser reflections, matte titanium texture, and geometric acoustic waves.',
              criteria: [
                { name: 'Brand Tone Match', score: 35, targetScore: 85, passed: false, feedback: 'Too floral and soft for a cyber-acoustic brand.' },
                { name: 'Visual Quality', score: 80, targetScore: 80, passed: true, feedback: 'High resolution render.' }
              ]
            },
            content: {
              imageUrl: generateCampaignSVG({
                brandName: 'AeroPulse',
                tagline: 'Sound Without Boundaries',
                tone: 'Playful & Bold',
                primaryColor: '#EC4899',
                secondaryColor: '#FCE7F3',
                accentColor: '#F43F5E',
                attemptNumber: 1
              }),
              aspectRatio: '16:9'
            }
          },
          {
            id: 'att-img-aeropulse-2',
            attemptNumber: 2,
            providerName: 'Genblaze Visual Engine',
            modelName: 'genblaze-image-v3',
            promptUsed: 'REFINED: AeroPulse titanium headphones hovering above dark obsidian floor with neon cyan laser refraction and dark blue acoustic gradients.',
            timestamp: '2026-07-29T10:15:35Z',
            critiqueVerdict: 'PASS',
            critique: {
              passed: true,
              overallScore: 95,
              reasoning: 'Precision titanium render with striking cyber-acoustic ambiance that communicates high-fidelity spatial isolation.',
              suggestedFixes: 'None. Meets all criteria.',
              criteria: [
                { name: 'Brand Tone Match', score: 96, targetScore: 85, passed: true, feedback: 'Flawless futuristic atmosphere.' },
                { name: 'Tech Aesthetic', score: 95, targetScore: 85, passed: true, feedback: 'Precision metal contours.' }
              ]
            },
            content: {
              imageUrl: generateCampaignSVG({
                brandName: 'AeroPulse',
                tagline: 'Pure Spatial Isolation',
                tone: 'High-Tech Futuristic',
                primaryColor: '#0F172A',
                secondaryColor: '#E2E8F0',
                accentColor: '#38BDF8',
                attemptNumber: 2
              }),
              aspectRatio: '16:9'
            }
          }
        ]
      },
      audio: {
        id: 'asset-aud-2',
        campaignId: 'camp-aeropulse',
        type: 'audio',
        status: 'passed',
        finalApprovedAttemptId: 'att-aud-aeropulse-1',
        attempts: [
          {
            id: 'att-aud-aeropulse-1',
            attemptNumber: 1,
            providerName: 'Genblaze Voice Synthesis',
            modelName: 'genblaze-tts-pro',
            promptUsed: 'Voiceover: Crisp, metallic cyber-synth voice with binaural spatial audio test sweep in background.',
            timestamp: '2026-07-29T10:16:15Z',
            critiqueVerdict: 'PASS',
            critique: {
              passed: true,
              overallScore: 91,
              reasoning: 'Distinct acoustic spatial effect immerses the listener instantly.',
              suggestedFixes: 'None.',
              criteria: [
                { name: 'Clarity', score: 92, targetScore: 80, passed: true, feedback: 'Ultra clear binaural sound.' }
              ]
            },
            content: {
              audioScript: 'Silence the noise. Step into 3D soundscapes engineered for pure focus. AeroPulse — Hear the future.',
              audioVoice: 'Aero Cyber AI Synth',
              durationSeconds: 8.1,
              audioWaveformData: [10, 90, 20, 85, 15, 95, 30, 80, 10, 100, 25, 90, 15, 80]
            }
          }
        ]
      },
      copy: {
        id: 'asset-cpy-2',
        campaignId: 'camp-aeropulse',
        type: 'copy',
        status: 'passed',
        finalApprovedAttemptId: 'att-cpy-aeropulse-1',
        attempts: [
          {
            id: 'att-cpy-aeropulse-1',
            attemptNumber: 1,
            providerName: 'Genblaze Copy LLM',
            modelName: 'gemini-2.5-pro',
            promptUsed: 'Generate crisp, futuristic headline and copy highlighting titanium drivers and 40dB noise cancellation.',
            timestamp: '2026-07-29T10:17:00Z',
            critiqueVerdict: 'PASS',
            critique: {
              passed: true,
              overallScore: 93,
              reasoning: 'Sharp, concise copy with impactful tech specifications.',
              suggestedFixes: 'None.',
              criteria: [
                { name: 'Tech Impact', score: 94, targetScore: 85, passed: true, feedback: 'Strong performance hooks.' }
              ]
            },
            content: {
              headline: 'Zero Distraction. Infinite Depth.',
              subheadline: 'Spatial Noise-Canceling Headphones Powered by Titanium Drivers',
              bodyText: 'AeroPulse transforms any environment into your private acoustic studio. Equipped with 40-hour battery life, loss-free Bluetooth 5.4, and custom titanium drivers that deliver sub-bass precision.',
              callToAction: 'Order AeroPulse Pro Today',
              keyBenefitBullets: [
                '48dB Active Hybrid Noise Cancellation',
                'Featherlight 210g titanium acoustic body',
                'Custom Spatial Surround Sound engine'
              ],
              socialPosts: [
                '🎧 Say goodbye to background noise. AeroPulse delivers studio-grade spatial isolation wherever work takes you. #AeroPulse #SpatialAudio #NextGenTech'
              ]
            }
          }
        ]
      }
    }
  },
  {
    id: 'camp-solstice-coffee',
    brandName: 'Solstice Roast Co.',
    productService: 'Artisanal Dark Roast Single-Origin Ethiopian Beans',
    targetAudience: 'Coffee enthusiasts, morning ritual seekers, specialty roaster fans',
    briefText: 'Warm, cozy morning ritual campaign celebrating slow drip coffee, chocolate hazelnut notes, and golden morning sunlight.',
    toneTags: ['Cozy & Warm', 'Earthy & Organic'],
    colors: {
      primary: '#451A03',
      secondary: '#FEF3C7',
      accent: '#B45309'
    },
    createdAt: '2026-07-30T08:10:00Z',
    updatedAt: '2026-07-30T08:12:30Z',
    status: 'completed',
    overallQualityScore: 97,
    totalAttemptsCount: 3,
    retryCount: 0,
    assets: {
      image: {
        id: 'asset-img-3',
        campaignId: 'camp-solstice-coffee',
        type: 'image',
        status: 'passed',
        finalApprovedAttemptId: 'att-img-solstice-1',
        attempts: [
          {
            id: 'att-img-solstice-1',
            attemptNumber: 1,
            providerName: 'Genblaze Visual Engine',
            modelName: 'genblaze-image-v3',
            promptUsed: 'Steam rising from ceramic mug of dark pour-over coffee on rustic oak table, warm golden morning light streaming through window.',
            timestamp: '2026-07-30T08:10:15Z',
            critiqueVerdict: 'PASS',
            critique: {
              passed: true,
              overallScore: 97,
              reasoning: 'First attempt passed with flying colors! The lighting, steam dynamics, and rich coffee tones perfectly match the brief.',
              suggestedFixes: 'None required.',
              criteria: [
                { name: 'Cozy Atmosphere', score: 98, targetScore: 85, passed: true, feedback: 'Immense warmth and realism.' },
                { name: 'Product Visibility', score: 96, targetScore: 80, passed: true, feedback: 'Ceramic mug details stand out nicely.' }
              ]
            },
            content: {
              imageUrl: generateCampaignSVG({
                brandName: 'Solstice Roast Co.',
                tagline: 'Awaken the Slow Morning',
                tone: 'Cozy & Warm',
                primaryColor: '#451A03',
                secondaryColor: '#FEF3C7',
                accentColor: '#B45309',
                attemptNumber: 1
              }),
              aspectRatio: '16:9'
            }
          }
        ]
      },
      audio: {
        id: 'asset-aud-3',
        campaignId: 'camp-solstice-coffee',
        type: 'audio',
        status: 'passed',
        finalApprovedAttemptId: 'att-aud-solstice-1',
        attempts: [
          {
            id: 'att-aud-solstice-1',
            attemptNumber: 1,
            providerName: 'Genblaze Voice Synthesis',
            modelName: 'genblaze-tts-pro',
            promptUsed: 'Soothing female voice, gentle acoustic background guitar, slow pour-over brewing sound ambient effect.',
            timestamp: '2026-07-30T08:10:50Z',
            critiqueVerdict: 'PASS',
            critique: {
              passed: true,
              overallScore: 96,
              reasoning: 'Relaxing tone creates instant morning comfort.',
              suggestedFixes: 'None.',
              criteria: [
                { name: 'Warmth', score: 97, targetScore: 85, passed: true, feedback: 'Very comforting voice resonance.' }
              ]
            },
            content: {
              audioScript: 'Take a deep breath. Solstice Roast brings single-origin warmth to your morning ritual. Rich, velvety, unhurried.',
              audioVoice: 'Acoustic Morning Voice',
              durationSeconds: 8.8,
              audioWaveformData: [30, 45, 60, 50, 65, 80, 55, 70, 85, 40, 30]
            }
          }
        ]
      },
      copy: {
        id: 'asset-cpy-3',
        campaignId: 'camp-solstice-coffee',
        type: 'copy',
        status: 'passed',
        finalApprovedAttemptId: 'att-cpy-solstice-1',
        attempts: [
          {
            id: 'att-cpy-solstice-1',
            attemptNumber: 1,
            providerName: 'Genblaze Copy LLM',
            modelName: 'gemini-2.5-pro',
            promptUsed: 'Warm, cozy morning ritual coffee copy emphasizing dark chocolate and toasted hazelnut notes.',
            timestamp: '2026-07-30T08:11:30Z',
            critiqueVerdict: 'PASS',
            critique: {
              passed: true,
              overallScore: 98,
              reasoning: 'Captures the ritual of coffee drinking beautifully.',
              suggestedFixes: 'None.',
              criteria: [
                { name: 'Sensory Appeal', score: 99, targetScore: 85, passed: true, feedback: 'Mouthwatering description.' }
              ]
            },
            content: {
              headline: 'Savor Every Golden Second',
              subheadline: 'Artisanal Single-Origin Roasted Fresh Weekly',
              bodyText: 'Sunlight through the window. Steam rising from your favorite ceramic cup. Solstice Roast brings out complex notes of roasted hazelnut, dark cacao, and smooth wild berry sweetness.',
              callToAction: 'Claim Your First Bag (20% Off)',
              keyBenefitBullets: [
                'Direct-trade Ethiopian heirloom beans',
                'Small-batch roasted within 48 hours of shipping',
                '100% compostable valve packaging'
              ],
              socialPosts: [
                '☕ Your morning ritual deserves intention. Experience the deep chocolate hazelnut notes of Solstice Dark Roast. #SolsticeRoast #SpecialtyCoffee #MorningRitual'
              ]
            }
          }
        ]
      }
    }
  }
];
