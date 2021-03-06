#!/usr/bin/env
"""
Computes the phase lag and time lag of energy channels of interest with a
reference energy band from the average cross spectrum. Can average over
frequency and over energy.

Reads from a FITS file where constants are in extension 0 header, cross spectrum
is in extension 1, power spectrum of interest bands are in extension 2, and
power spectrum of reference band is in extension 3.

Example call:
python get_lags.py ./cygx1_cs.fits ./cygx1_lags.fits ./cygx1_chan_energies.txt

Enter   python get_lags.py -h   at the command line for help.

"""
import argparse
import subprocess
import numpy as np
from astropy.io import fits
from astropy.io import ascii
from datetime import datetime
import os.path
import matplotlib.pyplot as plt
import matplotlib.font_manager as font_manager
from matplotlib.ticker import MultipleLocator
from matplotlib.ticker import ScalarFormatter

import tools  ## in https://github.com/abigailStev/whizzy_scripts

__author__ = "Abigail Stevens <A.L.Stevens at uva.nl>"
__year__ = "2015"
################################################################################
##
## November 2015, Federico M. Vincentelli:
## Minor adjustements for application to IR data
##
################################################################################
def get_inputs(in_file):
    """
    Gets cross spectrum, interest bands power spectra, reference band power
    spectrum, and necessary constants from the input FITS file. Constants come
    from header of extension 0, cross spectrum in table of extension 1, power of
    interest bands in extension 2, power of reference band in extension 3.

    2-D arrays of cross spectrum and interest bands were flattened (and are
    reshaped here)'C-style'.

    """
    try:
        fits_hdu = fits.open(in_file)
    except IOError:
        print "\tERROR: File does not exist: %s" % in_file
        exit()

    evt_list = fits_hdu[0].header['EVTLIST']
    dt = float(fits_hdu[0].header['DT'])
    n_bins = int(fits_hdu[0].header['N_BINS'])
    n_seg = int(fits_hdu[0].header['SEGMENTS'])
    exposure = float(fits_hdu[0].header['EXPOSURE'])
    detchans = int(
        fits_hdu[0].header['DETCHANS'])  # == number of interest bands
    rate_ci = np.asarray(fits_hdu[0].header['RATE_CI'])
    rate_ref = float(fits_hdu[0].header['RATE_REF'])
    n_seconds = n_bins * dt

    cs_data = fits_hdu[1].data
    powci_data = fits_hdu[2].data
    powref_data = fits_hdu[3].data

    try:
        cs_avg = np.reshape(cs_data.field('CROSS'), (n_bins / 2 + 1, detchans), \
                            order='C')
        power_ci = np.reshape(powci_data.field('POWER'),
                              (n_bins / 2 + 1, detchans), \
                              order='C')
    except ValueError:
        cs_avg = np.reshape(cs_data.field('CROSS'), (n_bins, detchans), \
                            order='C')
        power_ci = np.reshape(powci_data.field('POWER'), (n_bins, detchans), \
                              order='C')

    power_ref = powref_data.field('POWER')
    freq = powref_data.field('FREQUENCY')

    return freq, cs_avg, power_ci, power_ref, dt, n_bins, detchans, \
           n_seconds, n_seg, rate_ci, rate_ref, evt_list


################################################################################
def fits_out(out_file, in_file, evt_list, dt, n_bins, n_seg, detchans,
             lo_freq, up_freq, lo_energy, up_energy, mean_rate_ci,
             mean_rate_ref, freq, phase, err_phase, tlag, err_tlag, e_phase,
             e_err_phase, e_tlag, e_err_tlag):
    """
    Writes the lag-frequency and lag-energy spectra to a FITS output file.
    Header info is in extension 0, lag-frequency is in extension 1, and
    lag-energy is in extension 2. Arrays are flattened C-style before being
    saved as FITS tables.

    Parameters
    ----------
    out_file : str
        The full path of the output file.

    in_file : str
        The full path of the cross-spectrum input file.

    evt_list : str
        The full path of the event list of the data.

    dt : float
        Timestep of each bin in the light curve.

    n_bins : int
        The number of bins in one Fourier segment of the light curve.

    n_seg : int
        The number of Fourier segments averaged over to make the cross spectrum.

    detchans : int
        The number of detector energy channels in this data mode.

    lo_freq, up_freq : float
        The lower and upper frequency bounds to average over for computing the
        lag-energy spectrum. In Hz.

    lo_energy, up_energy : int
        The lower and upper energy bounds to average over for computing the
        lag-frequency spectrum. In detector energy channel.

    mean_rate_ci : np.array of floats
        The mean photon count rate of each of the cross-spectral channels of
        interest.

    mean_rate_ref : float
        The mean photon count rate of the cross-spectral reference band.

    freq : np.array of floats
        Fourier frequencies against which the lag-frequency spectrum is plotted.

    phase, err_phase : np.array of floats
        The phase and error in phase of the frequency lags, in radians.

    tlag, err_tlag : np.array of floats
        The time and error in time of the frequency lags, in seconds.

    e_phase, e_err_phase : np.array of floats
        The phase and error in phase of the energy lags, in radians.

    e_tlag, e_err_tlag : np.array of floats
        The time and error in time of the energy lags, in seconds.

    """

    chan = np.arange(0, detchans)
    f_bins = np.repeat(freq, len(chan))

    print "Output sent to: %s" % out_file

    ## Making FITS header (extension 0)
    prihdr = fits.Header()
    prihdr.set('TYPE', "Lag-frequency and lag-energy spectral data")
    prihdr.set('DATE', str(datetime.now()), "YYYY-MM-DD localtime")
    prihdr.set('EVTLIST', evt_list)
    prihdr.set('CS_DATA', in_file)
    prihdr.set('DT', dt, "seconds")
    prihdr.set('N_BINS', n_bins, "time bins per segment")
    prihdr.set('SEGMENTS', n_seg, "segments in the whole light curve")
    prihdr.set('EXPOSURE', n_seg * n_bins * dt,
               "seconds, of light curve")
    prihdr.set('DETCHANS', detchans, "Number of detector energy channels")
    prihdr.set('LAG_LF', lo_freq, "Hz")
    prihdr.set('LAG_UF', up_freq, "Hz")
    prihdr.set('LAG_LE', lo_energy, "Detector channel")
    prihdr.set('LAG_UE', up_energy, "Detector channel")
    prihdr.set('RATE_CI', str(mean_rate_ci.tolist()), "counts/second")
    prihdr.set('RATE_REF', mean_rate_ref, "counts/second")
    prihdu = fits.PrimaryHDU(header=prihdr)

    ## Making FITS table for lag-frequency plot (extension 1)
    col1 = fits.Column(name='FREQUENCY', format='D', array=f_bins)
    col2 = fits.Column(name='PHASE', unit='radians', format='D',
                       array=phase.flatten('C'))
    col3 = fits.Column(name='PHASE_ERR', unit='radians', format='D',
                       array=err_phase.flatten('C'))
    col4 = fits.Column(name='TIME_LAG', unit='s', format='D',
                       array=tlag.flatten('C'))
    col5 = fits.Column(name='TIME_LAG_ERR', unit='s', format='D',
                       array=err_tlag.flatten('C'))
    cols = fits.ColDefs([col1, col2, col3, col4, col5])
    tbhdu1 = fits.BinTableHDU.from_columns(cols)

    ## Making FITS table for lag-energy plot (extension 2)
    col1 = fits.Column(name='PHASE', unit='radians', format='D', array=e_phase)
    col2 = fits.Column(name='PHASE_ERR', unit='radians', format='D', \
                       array=e_err_phase)
    col3 = fits.Column(name='TIME_LAG', unit='s', format='D', array=e_tlag)
    col4 = fits.Column(name='TIME_LAG_ERR', unit='s', format='D', \
                       array=e_err_tlag)
    col5 = fits.Column(name='CHANNEL', unit='', format='I', \
                       array=chan)
    cols = fits.ColDefs([col1, col2, col3, col4, col5])
    tbhdu2 = fits.BinTableHDU.from_columns(cols)

    ## If the file already exists, remove it
    assert out_file[-4:].lower() == "fits", \
        'ERROR: Output file must have extension ".fits".'
    if os.path.isfile(out_file):
        subprocess.call(["rm", out_file])

    ## Writing to a FITS file
    thdulist = fits.HDUList([prihdu, tbhdu1, tbhdu2])
    thdulist.writeto(out_file)


################################################################################
def get_phase_err(cs_avg, power_ci, power_ref, n, M):
    """
    Computes the error on the complex phase (in radians) via the coherence.
    Power should NOT be Poisson noise-subtracted.

    Parameters
    ----------
    cs_avg : 2D np.array of complex numbers
        The cross spectrum, averaged over Fourier segments.

    power_ci : 2D np.array of floats
        The raw power in the channels of interest, averaged over Fourier
        segments.

    power_ref : np.array of floats
        The raw power in the reference band, averaged over Fourier segments.

    n : int
        The number of Fourier frequency bins being averaged together.

    M : int
        The number of segments averaged over

    Returns
    -------


    """
    with np.errstate(all='ignore'):
        a = power_ci * power_ref
        coherence = np.where(a != 0, np.abs(cs_avg) ** 2 / a, 0)
        phase_err = np.sqrt(np.where(coherence != 0, (1 - coherence) / \
                                     (2 * coherence * n * M), 0))

    return phase_err


################################################################################
def phase_to_tlags(phase, f):
    """
    Converts a complex-plane cross-spectrum phase (in radians) to a time lag
    (in seconds).

    Parameters
    ----------
    phase : float or np.array of floats
        The phase of the lag, in radians.

    f : float or np.array of floats
        The Fourier frequency of the cross-spectrum.

    Returns
    -------
    tlags : float or np.array of floats
        The time of the lag, in seconds.

    """
    assert np.shape(phase) == np.shape(f), "ERROR: Phase array must have same "\
            "dimensions as frequency array."

    with np.errstate(all='ignore'):
        tlags = np.where(f != 0, phase / (2.0 * np.pi * f), 0)

    return tlags


################################################################################
def plot_lag_freq(out_root, plot_ext, prefix, freq, phase, err_phase, tlag, \
                  err_tlag, lo_freq, up_freq, lo_energy, up_energy):
    """
	Plots the lag-frequency spectrum.
	
	"""

    font_prop = font_manager.FontProperties(size=20)

    name="_lag-frequency_%.2f-%.2fHz." %(lo_freq,up_freq)
    plot_file = out_root + name + plot_ext
    print "Lag-frequency spectrum: %s" % plot_file

    fig, ax = plt.subplots(1, 1, figsize=(10,7.5), dpi=300, tight_layout=True)
    ax.plot([freq[0], freq[-1]], [0, 0], lw=1.5, ls='dashed', c='black')
    # 	ax.plot([freq[0], freq[-1]],[np.pi,np.pi], lw=1.5, ls='dashed', c='black')
    # 	ax.plot([freq[0], freq[-1]],[-np.pi,-np.pi], lw=1.5, ls='dashed', c='black')
    # 	ax.errorbar(freq, phase, yerr=phase_err, lw=3, c='blue', \
    # 		ls='steps-mid', elinewidth=2, capsize=2)

    ax.errorbar(freq, tlag, yerr=err_tlag, lw=2, c='blue', \
                ls='steps-mid', capsize=2, elinewidth=2)
    ax.set_xlabel('Frequency (Hz)', fontproperties=font_prop)
    ax.set_ylabel('Time lag (s)', fontproperties=font_prop)

    # 	ax.set_ylabel('Phase lag (radians)', fontproperties=font_prop)
    ax.set_xlim(lo_freq, up_freq)
    ax.set_ylim(-0.1, 0.1)
    # 	ax.set_ylim(1.3*np.min(tlag), 1.30*np.max(tlag))
    # 	print np.min(tlag)
    # 	print np.max(tlag)
    # 	ax.set_ylim(-0.3, 0.3)
    # 	ax.set_ylim(-6, 6)
    ax.tick_params(axis='x', labelsize=18)
    ax.tick_params(axis='y', labelsize=18)
    title = "Lag-frequency spectrum, %s, channels %d - %d" % (prefix, lo_energy,
                                                              up_energy)
    ax.set_title(title, fontproperties=font_prop)

    plt.savefig(plot_file)
    # plt.show()
    plt.close()

# subprocess.call(['open', plot_file])


################################################################################
def plot_lag_energy(out_root, energies_tab, plot_ext, prefix, phase, err_phase,
        tlag, err_tlag, lo_freq, up_freq, detchans=64):
    """
    Plots the lag-energy spectrum.

    """
    font_prop = font_manager.FontProperties(size=18)
    energy_list = [np.mean([x, y]) for x,y in tools.pairwise(energies_tab)]
    energy_err = [np.abs(a-b) for (a,b) in zip(energy_list, energies_tab[0:-1])]
    e_chans = np.arange(0, detchans)
    name="lag-energy_%.2f-%.2fHz." %(lo_freq,up_freq)
    plot_file = out_root +"_" + name + plot_ext
    print "Lag-energy spectrum: %s" % plot_file

    ## Deleting the values at energy channel 10 for RXTE PCA event-mode data
    ## No counts detected in channel 10 in this data mode
    if detchans == 64 and len(phase) == 64:
        phase = np.delete(phase, 10)
        err_phase = np.delete(err_phase, 10)
        tlag = np.delete(tlag, 10)
        err_tlag = np.delete(err_tlag, 10)
        e_chans = np.delete(e_chans, 10)
        energy_list = np.delete(energy_list, 10)
        energy_err = np.delete(energy_err, 10)

		#####################
#	writes ascii file.dat with lag energy spectrum!
		#####################
    data_name=name +"dat" 
    data=[energy_list[2:26], tlag[2:26],energy_err[2:26],err_tlag[2:26]]
    print data
    ascii.write([energy_list[2:26], tlag[2:26],energy_err[2:26],err_tlag[2:26]],
            data_name,exclude_names=['y'])

#    data_name = data_name.replace("/lag_spectra/", "/lag_spectra/out_lags/GX339-4")

#    col1i = fits.Column(name='ENERGY',format= 'D', energy_list[2:26])
#    col2i = fits.Column(name='TIME_LAGS',format= 'D', array=tlag[2:26])
#    col3i = fits.Column(name='ERR_ENERGY',format= 'D', array=energy_err[2:26])
#    col4i = fits.Column(name='ERROR_TLAGS',format= 'D', array=err_tlag[2:26])
#    colsi = fits.ColDefs([col1i,col2i,col3i,col4I])
#    tbhdu = fits.BinTableHDU.from_columns(colsi)
#    thdulist = fits.HDUList([tbhdu])
#    thdulist.writeto('lag_energy.fits')

    #############
    ## Plotting!
    #############
    fig, ax = plt.subplots(1, 1, figsize=(10,7.5), dpi=300, tight_layout=True)

    ax.hlines(0.0, 3, 21, linestyle='dashed', lw=2, color='gray')
    ax.errorbar(energy_list[2:26], tlag[2:26], xerr=energy_err[2:26],
            yerr=err_tlag[2:26], ls='none', marker='o', ms=5, mew=2,
            mec='black', mfc='black', ecolor='black', elinewidth=2, capsize=0)

    # ax.errorbar(energy_list[5:200], tlag[5:200], xerr=energy_err[5:200], yerr=err_tlag[5:200], ls='none',
    #         marker='o', ms=5, mew=2, mec='black', mfc='black', ecolor='black',
    #         elinewidth=2, capsize=0)
    # ax.errorbar(energy_list, phase, xerr=energy_err, yerr=err_phase, ls='none',
    #         marker='+', ms=8, mew=2, mec='black', ecolor='black', elinewidth=2,
    #         capsize=0)

    ax.set_xlabel('Energy (keV)', fontproperties=font_prop)
    ax.set_xlim(3,21)
    # ax.set_xlim(0.3, 10)
    ax.set_xscale('log')
    x_maj_loc = [5,10,20]
    y_maj_loc = [-0.15, -0.1,-0.05, 0, 0.05, 0.1, 0.15]
    ax.set_xticks(x_maj_loc)
    ax.set_yticks(y_maj_loc)
    xLocator = MultipleLocator(1)  ## loc of minor ticks on x-axis
    yLocator = MultipleLocator(0.05)  ## loc of minor ticks on y-axis
    ax.xaxis.set_minor_locator(xLocator)
    ax.yaxis.set_minor_locator(yLocator)
    ax.xaxis.set_major_formatter(ScalarFormatter())

    ax.set_ylabel('Time lag (s)', fontproperties=font_prop)
    # ax.set_ylabel('Phase lag (radians)', fontproperties=font_prop)
    # ax.set_ylim(1.3 * np.min(tlag[2:25]), 1.30 * np.max(tlag[2:25]))
    ax.set_ylim(-0.17, 0.17)
    # ax.set_ylim(-0.4, 0.5)
    ax.tick_params(axis='x', labelsize=18)
    ax.tick_params(axis='y', labelsize=18)
    title = "Lag-energy spectrum, %s, %.2f - %.2f Hz" % (prefix, lo_freq,
                                                         up_freq)
    # ax.set_title(title, fontproperties=font_prop)

    plt.savefig(plot_file)
    # 	plt.show()
    plt.close()

################################################################################
def compute_lags(freq, cs_avg, power_ci, power_ref, dt, n_bins, detchans,
        n_seconds, n_seg, mean_rate_ci, mean_rate_ref, lo_freq, up_freq,
        lo_energy, up_energy):
    """
    Computing frequency lags and energy lags.

    Parameters
    ----------
    freq : np.array of floats
    cs_avg : 2D np.array of complex numbers
    power_ci : 2D np.array of floats
    power_ref : np.array of floats
    dt : float
    n_bins : int
    detchans : int
    n_seconds : int
    n_seg : int
    mean_rate_ci : np.array of floats
    mean_rate_ref : float
    lo_freq : float
    up_freq : float
    lo_energy : float
    up_energy : float

    Returns
    -------
    f_phase, f_err_phase, f_tlag, f_err_tlag, e_phase, e_err_phase,
            e_tlag, e_err_tlag
    """

    ## If cross spectrum contains positive and negative frequencies, only keep
    ## the positive ones
    if np.shape(cs_avg) == (n_bins, detchans):
        nyq_ind = np.argmax(freq) + 1  ## because in python, the scipy fft makes
                ## the nyquist frequency negative, and we want it to be
                ## positive! (it is actually both pos and neg)
        freq = np.abs(freq[0:nyq_ind + 1])  ## because it slices at end-1, and
                ## we want to include 'nyq_ind'; abs is because the nyquist freq
                ## is both pos and neg, and we want it pos here.
        cs_avg = cs_avg[0:nyq_ind + 1, ]
        power_ci = power_ci[0:nyq_ind + 1, ]
        power_ref = power_ref[0:nyq_ind + 1]

    assert np.shape(power_ci) == (n_bins / 2 + 1, detchans)
    assert np.shape(power_ref) == (n_bins / 2 + 1,)
    assert np.shape(cs_avg) == (n_bins / 2 + 1, detchans)
    assert np.shape(freq) == (n_bins / 2 + 1,)

    ###########################
    ## Averaging over energies
    ###########################

    e_span = up_energy - lo_energy + 1  ## including both ends
    erange_cs = np.mean(cs_avg[:, lo_energy:up_energy + 1], axis=1)
    erange_pow_ci = np.mean(power_ci[:, lo_energy:up_energy + 1], axis=1)
    erange_pow_ref = power_ref

    ################################################
    ## Getting lag and error for lag-frequency plot
    ################################################

    f_phase = -np.arctan2(erange_cs.imag, erange_cs.real)  ## Negative sign is
            ## so that a positive lag is a hard energy lag
    f_err_phase = get_phase_err(erange_cs, erange_pow_ci, erange_pow_ref, \
            e_span, n_seg)
    f_tlag = phase_to_tlags(f_phase, freq)
    f_err_tlag = phase_to_tlags(f_err_phase, freq)

    ##############################
    ## Averaging over frequencies
    ##############################

    if lo_freq in freq:
        f_span_low = np.argmax(freq == lo_freq)
    else:
        f_span_low = np.argmax(
            np.where(freq <= lo_freq))  ## The last True value
    if up_freq in freq:
        f_span_hi = np.argmax(freq == up_freq)
    else:
        f_span_hi = np.argmax(np.where(freq < up_freq)) + 1  ## The first False value

    f_span = f_span_hi - f_span_low + 1  ## including both ends
    frange_freq = freq[f_span_low:f_span_hi + 1]
    frange_cs = np.mean(cs_avg[f_span_low:f_span_hi + 1, ], axis=0)
    frange_pow_ci = np.mean(power_ci[f_span_low:f_span_hi + 1, ], axis=0)
    frange_pow_ref = np.repeat(np.mean(power_ref[f_span_low:f_span_hi + 1]), \
                               detchans)

    #############################################
    ## Getting lag and error for lag-energy plot
    #############################################

    e_phase = -np.arctan2(frange_cs.imag, frange_cs.real)  ## Negative sign is
            ## so that a positive lag is a hard energy lag ??
    e_err_phase = get_phase_err(frange_cs, frange_pow_ci, frange_pow_ref, \
            f_span, n_seg)
    f = np.repeat(np.mean(frange_freq), detchans)
    e_tlag = phase_to_tlags(e_phase, f)
    e_err_tlag = phase_to_tlags(e_err_phase, f)


    return f_phase, f_err_phase, f_tlag, f_err_tlag, e_phase, e_err_phase, \
            e_tlag, e_err_tlag


################################################################################
def main(in_file, out_file, energies_file, plot_root, prefix, plot_ext="eps",
        lo_freq=1.0, up_freq=10.0, lo_energy=2, up_energy=26):
    """
    Computes the phase lag and time lag from the average cross spectrum. Note
    that power_ci, power_ref, and cs_avg should be unnormalized and without
    noise subtracted.

    """
    print "get lags*************************************"
    energies_tab = np.loadtxt(energies_file)

    ## Get necessary information and data from the input file
    freq, cs_avg, power_ci, power_ref, dt, n_bins, detchans, n_seconds, \
            n_seg, mean_rate_ci, mean_rate_ref, evt_list = get_inputs(in_file)

    ######################
    ## Computing the lags
    ######################

    f_phase, f_err_phase, f_tlag, f_err_tlag, e_phase,e_err_phase, e_tlag, \
            e_err_tlag = compute_lags(freq, cs_avg, power_ci, power_ref, dt,
            n_bins, detchans, n_seconds, n_seg, mean_rate_ci,
            mean_rate_ref, lo_freq, up_freq, lo_energy, up_energy)

    ##########
    ## Output
    ##########

    fits_out(out_file, in_file, evt_list, dt, n_bins, n_seg, detchans,
            lo_freq, up_freq, lo_energy, up_energy, mean_rate_ci,
            mean_rate_ref, freq, f_phase, f_err_phase, f_tlag, f_err_tlag,
            e_phase, e_err_phase, e_tlag, e_err_tlag)

    ############
    ## Plotting
    ############

    plot_lag_freq(plot_root, plot_ext, prefix, freq, f_phase, f_err_phase,
            f_tlag, f_err_tlag, lo_freq, up_freq, lo_energy, up_energy)

    plot_lag_energy(plot_root, energies_tab, plot_ext, prefix, e_phase,
            e_err_phase, e_tlag, e_err_tlag, lo_freq, up_freq, detchans)


################################################################################
if __name__ == "__main__":

    ##############################################
    ## Parsing input arguments and calling 'main'
    ##############################################

    parser = argparse.ArgumentParser(usage="python get_lags.py infile outfile "\
            "[OPTIONAL ARGUMENTS]", description=__doc__,
            epilog="For optional arguments, default values are given in "\
            "brackets at end of description.")

    parser.add_argument('infile', help="Name of the FITS file containing the "\
            "cross spectrum, power spectrum of the channels of interest, and "\
            "power spectrum of the reference band.")

    parser.add_argument('outfile', help="Name of the FITS file to write the "\
            "lag spectra to.")

    parser.add_argument('energies_tab', help="Name of the txt file containing "\
            "a list of the keV energies that map to the detector energy "\
            "channels.")

    parser.add_argument('-o', dest='plot_root', default="./plot", help="Root "\
            "name for plots generated, to be appended with '_lag-freq.(ext"\
            "ension)' and '_lag-energy.(extension)'. [./plot]")

    parser.add_argument('--prefix', dest="prefix", default="--",
            help="The identifying prefix of the data (object nickname or "\
            "data ID). [--]")

    parser.add_argument('--ext', dest='plot_ext', default='eps',
            help="File extension for the plots. Do not include the dot. [eps]")

    parser.add_argument('--lf', dest='lo_freq', default=1.0,
            type=tools.type_positive_float, help="The lower limit of the "\
            "frequency range for the lag-energy spectrum to be computed for, "\
            "in Hz. [1.0]")

    parser.add_argument('--uf', dest='up_freq', default=10.0,
            type=tools.type_positive_float, help="The upper limit of the "\
            "frequency range for the lag-energy spectrum to be computed for, "\
            "in Hz. [10.0]")

    parser.add_argument('--le', dest='lo_energy', default=2,
            type=tools.type_positive_int, help="The lower limit of the energy "\
            "range for the lag-frequency spectrum to be computed for, in "\
            "detector channels. [2]")

    parser.add_argument('--ue', dest='up_energy', type=tools.type_positive_int,
            default=26, help="The upper limit of the energy range for the lag-"\
            "frequency spectrum to be computed for, in detector channels. [26]")

    args = parser.parse_args()

    main(args.infile, args.outfile, args.energies_tab, args.plot_root,
            args.prefix, plot_ext=args.plot_ext, lo_freq=args.lo_freq,
            up_freq=args.up_freq, lo_energy=args.lo_energy,
            up_energy=args.up_energy)


################################################################################
