from imgtools.io import read_dicom_series
from itertools import chain
from joblib import Parallel, delayed
from radiomics import featureextractor, imageoperations, logging
import radiomics

from yarea.image_processing import *
from yarea.loaders import *
from yarea.metadata import *
from yarea.negative_controls import *

def singleRadiomicFeatureExtraction(ctImage:sitk.Image,
                                    roiImage:sitk.Image,
                                    pyradiomicsParamFilePath:str = "data/default_pyradiomics.yaml",
                                    negativeControl:str = None):
    """Function to perform radiomic feature extraction for a single CT image and its corresponding segmentation.
       CT and segmentation will be aligned and cropped prior to extraction. 

    Parameters
    ----------
    ctImage : sitk.Image
        CT image to perform feature extraction on. Will be cropped and potentially generate a negative control (see negativeControl arg)
    roiImage : sitk.Image
        Region of interest (ROI) to extract radiomic features from within the CT.
    pyradiomicsParamFilePath : str
        Path to file containing configuration settings for pyradiomics feature extraction. Will use the provided config file in 'data/' by default if no file passed in.
    negativeControl : str
        Name of negative control to generate from the CT to perform feature extraction on. If set to None, will extract features from original CT image.

    Returns
    -------
    dict
        Dictionary containing image metadata, versions for key packages used for extraction, and radiomic features
    """
    # In case segmentation contains extra axis, flatten to 3D by removing it
    roiImage = flattenImage(roiImage)
    # Segmentation has different origin, align it to the CT for proper feature extraction
    alignedROIImage = alignImages(ctImage, roiImage)

    # Get pixel value for the segmentation
    segmentationLabel = getROIVoxelLabel(alignedROIImage)

    # Check that image and segmentation mask have the same dimensions
    if ctImage.GetSize() != alignedROIImage.GetSize():
        # Checking if number of segmentation slices is less than CT 
        if ctImage.GetSize()[2] > alignedROIImage.GetSize()[2]:  
            print("Slice number mismatch between CT and segmentation for", patID, ". Padding segmentation to match.")
            alignedROIImage = padSEGtoMatchCT(ctFolderPath, segFilePath, ctImage, alignedROIImage)
        else:
            raise RuntimeError()
    
    # Check that CT and segmentation correspond, segmentationLabel is present, and dimensions match
    segBoundingBox, correctedROIImage = imageoperations.checkMask(ctImage, alignedROIImage, label=segmentationLabel)
    # Update the ROI image if a correction was generated by checkMask
    if correctedROIImage is not None:
        alignedROIImage = correctedROIImage
    
    # Crop the image and mask to a bounding box around the mask to reduce volume size to process
    croppedCT, croppedROI = imageoperations.cropToTumorMask(ctImage, alignedROIImage, segBoundingBox)

    if negativeControl != None:
        print("Generating ", negativeControl, "negative control for CT.")
        croppedCT = applyNegativeControl(nc_type=negativeControl, baseImage=croppedCT, baseROI=croppedROI, roiLabel=segmentationLabel)

    # Extract features listed in the parameter file
    print("Calculating features for segmentation:", roi)

    # Load PyRadiomics feature extraction parameters to use
    # Initialize feature extractor with parameters
    featureExtractor = featureextractor.RadiomicsFeatureExtractor(pyradiomicsParamFilePath)

    # Extract radiomic features from CT with segmentation as mask
    idFeatureVector = featureExtractor.execute(croppedCT, croppedROI, label=segmentationLabel)

    return idFeatureVector


def radiomicFeatureExtraction(imageMetadataPath:str,
                              imageDirPath:str,
                              roiNames:str = None,
                              pyradiomicsParamFilePath:str = "data/default_pyradiomics.yaml",
                              outputFilePath:str = None,
                              negativeControl:str = None,
                              parallel:bool = False,):
    """Perform radiomic feature extraction using PyRadiomics on CT images with a corresponding segmentation.
       Utilizes outputs from med-imagetools (https://github.com/bhklab/med-imagetools) run on the image dataset.

    Parameters
    ----------
    imageMetadataPath : str
        Path to csv file created by matchCTtoSegmentation function that contains a CT and matching segmentation in each row.
    imageDirPath : str
        Path to the directory containing the directory of CT and segmentation images. This directory should contain the .imgtools directory from the med-imagetools run
        and be the same as the input path used in med-imagetools
    roiNames : str
        Name pattern for the ROIs to load for the RTSTRUCTs. Can be None for DICOM SEG segmentations.
    pyradiomicsParamFilePath : str
        Path to file containing configuration settings for pyradiomics feature extraction. Will use the provided config file in 'data/' by default if no file passed in.
    outputFilePath : str
        Path to save the dataframe of extracted features to as a csv
    negativeControl : str
        Name of negative control to generate from the CT to perform feature extraction on. If set to None, will extract features from original CT image.
    parallel : bool
        Flag to decide whether to run extraction in parallel. 
    
    Returns
    -------
    pd.DataFrame
        Dataframe containing the image metadata and extracted radiomic features.
    """
    # Setting pyradiomics verbosity lower
    logger = logging.getLogger("radiomics")
    logger.setLevel(logging.ERROR)

    # Load in summary file generated by radiogenomic_pipeline
    pdImageInfo = pd.read_csv(imageMetadataPath, header=0)

    # Get array of unique CT series' IDs to iterate over
    ctSeriesIDList = pdSummaryFile["series_CT"].unique()

    def featureExtraction(ctSeriesID):
        ''' Function to extract PyRadiomics features for all ROIs present in a CT. Inner function so it can be run in parallel with joblib.'''
        # Get all info rows for this ctSeries
        ctSeriesInfo = pdImageInfo.loc[pdImageInfo["series_CT"] == ctSeriesID]
        patID = seriesInfo.iloc[0][idColumnName]

        print("Processing ", patID)

        # Get absolute path to CT image files 
        ctFolderPath = os.path.join(imageDirPath, ctSeriesInfo.iloc[0]['folder_CT'])
        # Load CT by passing in specific series to find in a directory
        ctImage = read_dicom_series(path = ctFolderPath, series_id = ctSeriesID)

        # Get list of segmentations to iterate over
        segSeriesIDList = ctSeriesInfo['series_seg'].unique()

        # Initialize dictionary to store radiomics data for each segmentation (image metadata + features)
        ctAllData = []

        # Loop over every segmentation associated with this CT - only loading CT once
        for segCount, segSeriesID in enumerate(segSeriesIDList):
            segSeriesInfo = ctSeriesInfo.loc[ctSeriesInfo['series_seg'] == segSeriesID]

            # Check that a single segmentation file is being processed
            if len(segRow) > 1:
                # Check that if there are multiple rows that it's not due to a CT with subseries (this is fine, the whole series is loaded)
                if not segRow.duplicated(subset=['series_CT'], keep=False).all():
                    raise RuntimeError("Some kind of duplication of segmentation and CT matches not being caught. Check seg_and_ct_dicom_list in radiogenomic_output.")
            
            # Get absolute path to segmentation image file
            segFilePath = os.path.join(imageDirPath, segSeriesInfo.iloc[0]['file_path_seg'])
            # Get dictionary of ROI sitk Images for this segmentation file
            segImages = loadSegmentation(segFilePath, modality = segSeriesInfo.iloc[0]['modality_seg'], originalImageDirPath=ctFolderPath, roiNames=roiNames)
            
            # Check that this series has ROIs to extract from (dictionary isn't empty)
            if not segImages:
                print('CT ', ctSeriesID, 'and segmentation ',segSeriesID, ' has no ROIs or no ROIs with the label ', roiNames, '. Moving to next segmentation.')

            else:
                # Loop over each ROI contained in the segmentation to perform radiomic feature extraction
                for roiCount, roiImageName in enumerate(segImages):
                    # ROI counter for image metadata output
                    roiNum = roiCount + 1

                    # Exception catch for if the segmentation dimensions do not match that original image
                    try:
                        # Extract radiomic features from this CT/segmentation pair
                        idFeatureVector = singleRadiomicFeatureExtraction(ctImage, roiImage = segImages[roiImageName],
                                                                          pyradiomicsParamFilePath = pyradiomicsParamFilePath,
                                                                          negativeControl = negativeControl)

                        # Create dictionary of image metadata to append to front of output table
                        sampleROIData = {"patient_ID": patID,
                                        "study_UID": segRow.iloc[0]['study_CT'],
                                        "study_description": segRow.iloc[0]['study_description_CT'],
                                        "series_UID": segRow.iloc[0]['series_CT'],
                                        "series_description": segRow.iloc[0]['series_description_CT'],
                                        "image_modality": segRow.iloc[0]['modality_CT'],
                                        "instances": segRow.iloc[0]['instances_CT'],
                                        "seg_series_UID": segRow.iloc[0]['series_seg'],
                                        "seg_modality": segRow.iloc[0]['modality_seg'],
                                        "seg_ref_image": segRow.iloc[0]['reference_ct_seg'],
                                        "roi": roi,
                                        "roi_number": roiNum,
                                        "negative_control": nc_type}

                        # Concatenate image metadata with PyRadiomics features
                        sampleROIData.update(idFeatureVector)
                        # Store this ROI's info in the segmentation level list
                        ctAllData.append(sampleROIData)

                    except Exception as e:
                        print(str(e))

        return ctAllData
        ###### END featureExtraction #######

    # Extract radiomic features for each CT, get a list of dictionaries
    # Each dictioary contains features for each ROI in a single CT
    if not parallel:
        # Run feature extraction over samples in sequence - will be slower
        features = [featureExtraction(ctSeriesID) for ctSeriesID in ctSeriesIDList]
    else:
        # Run feature extraction in parallel
        features = Parallel(n_jobs=-1, require='sharedmem')(delayed(featureExtraction)(ctSeriesID) for ctSeriesID in ctSeriesIDList)
    
    # Flatten the list of dictionaries (happens when there are multiple ROIs or SEGs associated with a single CT)
    flatFeatures = list(chain.from_iterable(features))
    # Convert list of feature sets into a pandas dataframe to save out
    featuresTable = pd.DataFrame(flatFeatures)

    # Save out features
    if outputFilePath != None:
        saveDataframeCSV(featuresTable, outputFilePath)

    return featuresTable