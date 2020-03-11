#!/usr/bin/env python3
'''
Portland State Aerospace Society

GPS signal acquisition

'''

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import configparser

import GoldCode
from GPSData import IQData, DataType

GPS_fs = 4.092e6 # Sampling Frequency [Hz]
global GPS_verbosity 

def main():
    '''
    Acquires data from default file when Acquisition.py is run directly
    '''
    # Need these to pass to importFile module
    numberOfMilliseconds = 10
    sampleLength = numberOfMilliseconds / 1000.0
    bytesToSkip = 0#71000000

    data = IQData()
    # Uncomment one of these lines to choose between Launch12 or gps-sdr-sim data

    # /home/evan/Capstone/gps/resources/JGPS@-32.041913222
    data.importFile('c:/Users/jdiamond/source/repos/gps-sdr-sim/gpssim.bin', GPS_fs, sampleLength, bytesToSkip, False, DataType.S8IQ)
    #data.importFile('./resources/JGPS@-32.041913222', GPS_fs, sampleLength, bytesToSkip)
    #data.importFile('../resources/test.max', GPS_fs, sampleLength, bytesToSkip)

    results = acquire(data,block_size_ms=numberOfMilliseconds)


class SatStats:
    def __init__(self):
        self.Acquired = False
        self.MaxSNR = None
        self.DopplerHz = None
        self.FineFrequencyEstimate = None
        self.CodePhaseSamples  = None
        self.CodePhaseChips = None
        self.PeakToSecond = []

class AcquisitionResult:
    '''
    Struct that contains the result of the acquisition process for one satellite. Gets
    passed to Tracking.py and used to initialize the loops.

    # Contents
    satellite: specified on creation, integer used to specify satellite
    codePhase: detected code phase after acquisition
    carrFreq : detected carrier frequency after acquisition
    '''

    def __init__(self, SV):
        #Primary info for tracking
        self.satellite = SV
        self.codePhase = 0
        self.carrFreq  = 0

        #Additional info for the director module
        if GPS_directed:
            self.pSNR

def acquire(data, block_size_ms=10, bin_list=range(-10000,10000, 100), sat_list=range(1, 33),
            show_final_plot=True, save_sat_results=False):
    '''
    Searches for GPS satellites in a raw IQ stream. File must be encodede to the
    specifications found in the README

    ## Args:

    data: gps.IQData object that has already been trimmed to length.

    ## kwArgs:
    bin_list: int list of frequency bins to search across. Defaults to 8kHz above and below carrier
    in 100Hz steps.

    sat_list: int list of SVs to use in acquisition. Defaults to the 32 active GPS satellites.

    showFinalPlot: bool determines whether matplotlib displays a bar graph of the final acquisition
    results. Defaults to True.

    saveSatResults: bool determines whether matplotlib saves a plot of each SV's frequency search.
    Defaults to False.

    ## Returns:
    object containing acquisition results

    '''
    
    
    # Create array to store max values, freq ranges, per satellite
    satInfoList = []
    for x in range(33):
        satInfoList.append(SatStats())
    maxVals = np.zeros(len(sat_list) + 1)

    satInd = 0
    # Loop through selected satellites
    for curSat in sat_list:
        print("Searching for SV " + str(curSat) + "...")
        
        #Grab a CA Code
        CACode = GoldCode.getAcquisitionCode(curSat,  GPS_fs / 1.023e6)

        # Repeat entire array for each ms of data sampled
        CACodeSampled = np.tile(CACode, int(data.sampleTime*1000))

        #CHECK
        acqResult = findSat(data, CACodeSampled, bin_list, block_size_ms)
        satInfoList[satInd+1] = acqResult

        if save_sat_results:
            plt.figure()
            plt.plot(bin_list, SatInfo[satInd].PeakToSecond)
            plt.ylim((0, 20))
            plt.xlabel('Doppler Shift (Hz)')
            plt.ylabel('Peak-to-SecondLargest ratio (dB)')
            plt.title("Sat %d - PeakToSecondLargest"%curSat)
            plt.show()


        maxVals[satInd + 1] = np.amax(satInfoList[satInd+1].PeakToSecond)

        satInd = satInd+1

    if show_final_plot:
        _outputplot(maxVals)
        _outputTable(satInfoList)
    return satInfoList

def findSat(data,  code, bins, block_size_ms=10, tracking = False):
    '''
    Searches IQ Data for a single satellite across all specified frequencies.

    ## Args:

    data: gps.IQData object that has already been trimmed to length.

    code: C/A code for the desired satellite that has been generated, sampled,
    and extended.

    bins: a list of integers where each element is a frequency at which acquisition 
    will be done.

    ## kwArgs:


    ## Returns:
    object containing acquisition results for the satellite

    '''
    ms_samples = int(GPS_fs / 1000)
    dataBlock = data.CData[0:(ms_samples*block_size_ms)]
    timeBlock = data.t[0:(ms_samples*block_size_ms)]
    NsamplesBlock = ms_samples*block_size_ms

    # Place to store current satellite information
    curSatInfo = SatStats()

    SNR_THRESHOLD = 3.4
    #if tracking is True:
    peakToSecondList = np.zeros(len(bins))
    codePhaseList = np.zeros(len(bins))
    SNRList = np.zeros(len(bins))

    codefft = np.fft.fft(code, len(dataBlock))
    GCConj = np.conjugate(codefft)
    
    N = len(bins)
    freqInd = 0
    # Loop through all frequencies
    for n, curFreq in enumerate(bins):
        
        # Shift frequency to baseband using complex exponential
        CDataShifted = dataBlock*np.exp(-1j*2*np.pi*curFreq*timeBlock)
        fftCDataShifted = np.fft.fft(CDataShifted, NsamplesBlock)

        # Mix code fft and take inverse
        result = np.fft.ifft(GCConj * fftCDataShifted, NsamplesBlock)

        resultSQ = np.real(result * np.conjugate(result))

        rmsPowerdB = 10*np.log10(np.mean(resultSQ))
        resultdB = 10*np.log10(resultSQ)

        codePhaseInSamples = np.argmax(resultSQ[0:ms_samples])

        # Search for secondlargest value in 1 ms worth of data
        secondLargestValue = _GetSecondLargest(resultSQ[0:int(data.sampleFreq*0.001)])

        # Pseudo SNR
        firstPeak = np.amax(resultSQ[0:ms_samples])
        peakToSecond =  10*np.log10(  firstPeak/secondLargestValue  )

        curSatInfo.PeakToSecond.append(peakToSecond)

        #if tracking is True:
        peakToSecondList[n] = peakToSecond
        codePhaseList[n] = codePhaseInSamples
        SNRList[n] = 10*np.log10(  firstPeak/np.mean(resultSQ)  )

        # Don't print data when correlation is probably not happening
        if peakToSecond > SNR_THRESHOLD:
            print("Possible acquisition: Freq: %8.4f, Peak2Second: %8.4f, Code Phase (samples): %8.4f"
                  %(curFreq, peakToSecond, codePhaseInSamples))

        freqInd = freqInd + 1

        # Percentage Output
        print("%02d%%"%((n/N)*100), end="\r")
   
    peakToSecondMaxBin = np.argmax(peakToSecondList)
    curSatInfo.MaxSNR = SNRList[peakToSecondMaxBin]
    curSatInfo.DopplerHz = bins[peakToSecondMaxBin]
    curSatInfo.CodePhaseSamples = codePhaseList[peakToSecondMaxBin]
    L1SampleRatio = (1.023*10**6)/(4.092*10**6)
    curSatInfo.CodePhaseChips = 1023 - L1SampleRatio*curSatInfo.CodePhaseSamples

    # Check if Acquisition was successful for this satellite
    if np.amax(curSatInfo.PeakToSecond) >= SNR_THRESHOLD:
        curSatInfo.Acquired = True

    # Get fine-frequency (If acquired):
    if curSatInfo.Acquired == True:
        # Already have a CA code that is at least 1 ms in length
        CACode = code[0:ms_samples] # store first ms

        # Repeat entire array 5 times for 5 ms
        code5ms = np.tile(CACode, int(5))

        #GetFineFrequency(data,curSatInfo,code5ms)

    return curSatInfo

def GetFineFrequency(data, SatInfo, code5ms): # now passed in data class
    # Performs fine-frequency estimation. In this case, data will be a slice
    # of data (probably same length of data that was used in the circular
    # cross-correlation)

    
    Ts = 1/GPS_fs
    ms_samples =int(0.001*GPS_fs)

    # Medium-frequency estimation data length (1ms in book, but may need to used
    # the data length from acquisition)
    numMSmf = 1 # num ms for medium-frequency estimation
    Nmf = int(np.ceil(numMSmf*ms_samples))  # num of samples to use for medium-frequency estimation (and DFT)

    dataMF = data.CData[0:(ms_samples*numMSmf)]

    # Create list of the three frequencies to test for medium-frequency estimation.
    k = []
    k.append(SatInfo.DopplerHz - 400*10**3)
    k.append(SatInfo.DopplerHz)
    k.append(SatInfo.DopplerHz + 400*10**3)

    # Create sampled time array for DFT
    nTs = np.linspace(0,Ts*(Nmf + 1),Nmf,endpoint=False)

    # Perform DFT at each of the three frequencies.
    X = []
    X.append(np.abs(sum(dataMF*np.exp(-2*np.pi*1j*k[0]*nTs)))**2)
    X.append(np.abs(sum(dataMF*np.exp(-2*np.pi*1j*k[1]*nTs)))**2)
    X.append(np.abs(sum(dataMF*np.exp(-2*np.pi*1j*k[2]*nTs)))**2)

    # Store the frequency value that has the largest power
    kLargest = k[np.argmax(X)]
    print("Largest of three frequencies: %f"%kLargest) # Will remove. Temporarily for debugging purposes.

    # Get 5 ms of consecutive data, starting at beginning of CA Code
    CACodeBeginning = int(SatInfo.CodePhaseSamples)
    data5ms = data.CData[CACodeBeginning:int(5*ms_samples) + CACodeBeginning]

    # Get 5 ms of CA Code, with no rotation performed.
    # passed in from function (code5ms)

    # Multiply data with ca code to get cw signal
    dataCW = data5ms*code5ms

    # Perform DFT on each of the ms of data (5 total), at kLargest frequency.
    # Uses variables from medium-frequency, so if they change, may need to re-create below.
    X = []
    PhaseAngle = []
    for i in range(0,5):
        X.append(sum(dataCW[i*ms_samples:(i+1)*ms_samples]*np.exp(-2*np.pi*1j*kLargest*nTs)))
        PhaseAngle.append(np.arctan(np.imag(X[i])/np.real(X[i])))
        print("Magnitude: %f" %X[i])
        print("Phase Angle: %f" %PhaseAngle[i])

    # Get difference angles
    PhaseDiff = []
    for i in range(1,5):
        PhaseDiff.append(PhaseAngle[i]-PhaseAngle[i-1])
        print("Phase difference %d, is: %f"%((i-1),PhaseDiff[i-1]))

    # Adjust phases so magnitude not greater than 2.3*pi/5
    # WIP
    PhaseThreshold = (2.3*np.pi)/5
    for (i,curPhaseDiff) in enumerate(PhaseDiff):
        if np.abs(curPhaseDiff) > PhaseThreshold:
            curPhaseDiff = PhaseDiff[i] - 2*np.pi
            if np.abs(curPhaseDiff) > PhaseThreshold:
                curPhaseDiff = PhaseDiff[i] + 2*np.pi
                if np.abs(curPhaseDiff) > (2.2*np.pi)/5:
                    curPhaseDiff = PhaseDiff[i] - np.pi
                    if np.abs(curPhaseDiff) > PhaseThreshold:
                        curPhaseDiff = PhaseDiff[i] - 3*np.pi
                        if np.abs(curPhaseDiff) > PhaseThreshold:
                            curPhaseDiff = PhaseDiff[i] + np.pi
        PhaseDiff[i] = curPhaseDiff
    fList = (np.array(PhaseDiff)/(2*np.pi*0.001))
    print(fList)
    print(np.mean(fList))

    FineFrequencyEst = 0 # Just a placeholder.
    return FineFrequencyEst

def _outputTable(satInfoList):
    print("|-----+---------+----------+------------+---------+------------+------------|")
    print("| PRN | Max SNR | Peak-To- | P2S / P2S- | Doppler | Code Phase | Code Phase |")
    print("|     |  (dB)   |  Second  | mean [dB]] |   [Hz]  |   [Chips]  |  [Samples] |")
    print("|-----+---------+----------+------------+---------+------------+------------|")
    for i in range(1,33):
        P2SToMeanP2SdB = 10*np.log10(  np.amax(satInfoList[i].PeakToSecond)/np.mean(satInfoList[i].PeakToSecond)  )
        if satInfoList[i].Acquired == True:
            print("| %2d  %8.3f  %8.3f    %8.3f      %6d    %9.3f    %6d     |"
                  %(i,satInfoList[i].MaxSNR, np.amax(satInfoList[i].PeakToSecond), P2SToMeanP2SdB , satInfoList[i].DopplerHz,satInfoList[i].CodePhaseChips, satInfoList[i].CodePhaseSamples))
    print("|-----+---------+----------+------------+---------+------------+------------|")

def _outputplot(ratios):
    '''
    Outputs a formatted matplotlib plot of the highest pseudo-SNR value for each SW across all
    frequencies.
    '''

    ran = np.arange(len(ratios))
    fig, ax = plt.subplots(figsize=[10, 8])

    #Use highest correlations for the 6 highest channels
    channels = np.argpartition(ratios, -6)[-6:]

    ax.bar(ran, ratios, linewidth=0, color='#aec7e8', align='center')
    #ax.set_axis_bgcolor('#e3ecf9')

    childrenLS = ax.get_children()
    barlist = filter(lambda x: isinstance(x, matplotlib.patches.Rectangle), childrenLS)

    for n, bar0 in enumerate(barlist):
        if n in channels:
            bar0.set_color('#ffbb78')
            bar0.edgecolor = 'b'
            bar0.linewidth = 6
        elif (n != 33) and ratios[n] > 3.0:
            bar0.set_color('#98df8a')

    plt.xlim([0, len(ratios) + 1])
    plt.title('Acquisition Results')
    plt.ylabel('Ratio of top 2 peaks (abs squared)')
    plt.xlabel('Satellite')
    plt.show()

def _GetSecondLargest(DataList):
    '''
    Returns the second largest value in an array
    '''
    # This will return second largest value
    # It will also ignore any value that is close to the second largest value

    # Make sure is a numpy array
    DataArray = np.array(DataList)

    # Find largest value
    Largest = np.amax(DataArray)
    LargestIndex = np.argmax(DataArray)
    #print("Largest value: %f, at position: %d"%(Largest,LargestIndex))

    # Reduce value by a percent to prevent near-identical values from being selected
    ScaleAmount = 0.95
    ScaledLargest = ScaleAmount*Largest
    SecondLargest = 0
    SecondLargestIndex = 0

    for ind, val in enumerate(DataArray):
        if val < ScaledLargest:
            if val > SecondLargest:
            #Ignore adjacent bins to Largest
                if np.abs(LargestIndex-ind) > 100:
                    SecondLargest = val
                    SecondLargestIndex = ind

    #print("Second largest value: %f, at position: %d"%(SecondLargest,SecondLargestIndex))
    return SecondLargest


if __name__ == "__main__":
    main()
