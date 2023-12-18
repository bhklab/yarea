from yarea.loaders import *
from yarea.feature_extraction import *

import pytest
import collections

@pytest.fixture
def nsclcCTImage():
    nsclcCTPath = "tests/NSCLC_Radiogenomics/R01-001/09-06-1990-NA-CT_CHEST_ABD_PELVIS_WITH_CON-98785/3.000000-THORAX_1.0_B45f-95741"
    return loadDicomSITK(nsclcCTPath)

@pytest.fixture
def nsclcSEGImage():
    nsclcSEGPath = "tests/NSCLC_Radiogenomics/R01-001/09-06-1990-NA-CT_CHEST_ABD_PELVIS_WITH_CON-98785/1000.000000-3D_Slicer_segmentation_result-67652/1-1.dcm"
    segDictionary = loadSegmentation(nsclcSEGPath, modality = 'SEG')
    return segDictionary['Heart']

@pytest.fixture
def lung4DCTImage():
    lung4DCTPath = "tests/4D-Lung/113_HM10395/11-26-1999-NA-p4-13296/1.000000-P4P113S303I10349 Gated 40.0B-29543"
    return loadDicomSITK(lung4DCTPath)

@pytest.fixture
def lung4DRTSTRUCTImage():
    lung4DRTSTRUCTPath = "tests/4D-Lung/113_HM10395/11-26-1999-NA-p4-13296/1.000000-P4P113S303I10349 Gated 40.0B-47.35/1-1.dcm"
    lung4DCTPath = "tests/4D-Lung/113_HM10395/11-26-1999-NA-p4-13296/1.000000-P4P113S303I10349 Gated 40.0B-29543"
    segDictionary = loadSegmentation(lung4DRTSTRUCTPath, modality = 'RTSTRUCT',
                                     baseImageDirPath = lung4DCTPath, roiNames = 'Tumor_c.*')
    return segDictionary['Tumor_c40']

@pytest.fixture
def pyradiomicsParamFilePath():
    return "src/yarea/data/default_pyradiomics.yaml"

def test_singleRadiomicFeatureExtraction_SEG(nsclcCTImage, nsclcSEGImage, pyradiomicsParamFilePath):
    """Test single image feature extraction with a CT and SEG"""

    actual = singleRadiomicFeatureExtraction(nsclcCTImage, nsclcSEGImage, pyradiomicsParamFilePath)
    assert type(actual) == collections.OrderedDict, \
        "Wrong return type, expect a collections.OrderedDict"
    assert len(actual) == 1353, \
        "Wrong return size, check pyradiomics parameter file is correct"
    assert actual['diagnostics_Configuration_Settings']['label'] == 255, \
        "Wrong label getting passed for ROI"
    assert actual['diagnostics_Image-original_Size'] == (26, 21, 20), \
        "Cropped CT image is incorrect size"
    assert actual['diagnostics_Mask-original_Size'] == (26, 21, 20), \
        "Cropped segmentation mask is incorrect size"
    assert actual['diagnostics_Mask-original_Size'] == actual['diagnostics_Image-original_Size'], \
        "Cropped CT and segmentation mask dimensions do not match"
    assert actual['original_shape_MeshVolume'].tolist()== pytest.approx(1273.7916666666667), \
        "Volume feature is incorrect"

def test_singleRadiomicFeatureExtraction_RTSTRUCT(lung4DCTImage, lung4DRTSTRUCTImage, pyradiomicsParamFilePath):
    """Test single image feature extraction with a CT and RTSTRUCT"""

    actual = singleRadiomicFeatureExtraction(lung4DCTImage, lung4DRTSTRUCTImage, pyradiomicsParamFilePath)
    assert type(actual) == collections.OrderedDict, \
        "Wrong return type, expect a collections.OrderedDict"
    assert len(actual) == 1353, \
        "Wrong return size, check pyradiomics parameter file is correct"
    assert actual['diagnostics_Configuration_Settings']['label'] == 1, \
        "Wrong label getting passed for ROI"
    assert actual['diagnostics_Image-original_Size'] == (51, 92, 28), \
        "Cropped CT image is incorrect size"
    assert actual['diagnostics_Mask-original_Size'] == (51, 92, 28), \
        "Cropped segmentation mask is incorrect size"
    assert actual['diagnostics_Mask-original_Size'] == actual['diagnostics_Image-original_Size'], \
        "Cropped CT and segmentation mask dimensions do not match"
    assert actual['original_shape_MeshVolume'].tolist()== pytest.approx(66346.66666666667), \
        "Volume feature is incorrect"