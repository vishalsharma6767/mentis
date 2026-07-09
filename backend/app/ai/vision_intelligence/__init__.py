"""Vision Intelligence Engine — Mentis Phase 3.

Transforms raw camera images into structured EducationalScene objects
so the Teacher Agent receives rich educational understanding instead
of raw OCR text.

Pipeline stages:
  1. Image Preprocessor    — enhance, deskew, correct perspective, score quality
  2. Document Detector     — detect notebook / book / worksheet / whiteboard
  3. Layout Analyzer       — identify headings, questions, regions, margins
  4. OCR Engine            — printed + handwritten text (English, Hindi, Hinglish)
  5. Handwriting Engine    — messy notes, corrections, arrows, strikes
  6. Formula Engine        — math, physics, chemistry, stats expressions
  7. Diagram Engine        — geometry, circuits, biology, flowcharts
  8. Graph Engine          — axes, trends, points, curves
  9. Question Extractor    — separate question from answer from notes
  10. Topic Classifier     — subject, chapter, concept
  11. Difficulty Estimator — problem difficulty level
  12. Scene Builder        — assemble all into EducationalScene
  13. Vision Validator     — reject low-confidence predictions, request recapture
"""

from app.ai.vision_intelligence.schema import (
    BoundingBox,
    ImageQuality,
    PageRegion,
    TextBlock,
    BlockType,
    Formula,
    FormulaType,
    Diagram,
    DiagramType,
    Graph,
    DetectedMistake,
    MistakeType,
    Question,
    DetectedTable,
    EducationalScene,
    SceneConfidence,
    SceneMetadata,
)
