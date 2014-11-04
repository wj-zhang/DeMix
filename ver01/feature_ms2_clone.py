import sys
import os
import csv
import pandas
import numpy
import pymzml
import xml

MS1_Precision = 8e-6

def load_feature_table(fn):
    table = []
    with open(fn, 'r') as fh:
        rd = csv.reader(fh, delimiter=',')
        for row in rd:
            if row[0] == 'FEATURE':
                _, rt, mz, _, chg, _, _, _, _, rtl, rtr = row
                table.append([float(mz), int(chg), float(rtl), float(rtr), float(rt)])
    table.sort(key=lambda x: x[3])
    return table

def load_PSM(fn):
    psm = pandas.read_table(fn)
    psm = psm[psm.QValue <=0.001]
    return psm


def spectra_clone(feature_fn, mzml_fn, first_psm, full_iso_width=4.0):
    features = load_feature_table(feature_fn)
    iso_width = full_iso_width / 2.0
    dm_offset = first_psm['PrecursorError(ppm)'].mean()
    max_scan = first_psm.ScanNum.max()
    sys.stderr.write("Auto correct precursor m/z offset: %.2f ppm \n" % dm_offset)
    
    if mzml_fn.endswith('.gz'):
        fh = gzip.open(mzml_fn)
    else:
        fh = open(mzml_fn)
    
    outpath = "%s.demix.mgf" % mzml_fn
    sys.stdout = open(outpath, 'wb')

    speciter = pymzml.run.Reader(mzml_fn)
    timescale = 0
    try:
        for spec in speciter:
            element = spec.xmlTree.next()
            title = element.get('id')
            idx = int(title.split('scan=')[-1])

            if idx % 1000 == 0:
                sys.stderr.write("DeMix %d MS/MS (~%.1f%%)\n" % (idx, idx * 100.0 / max_scan))

            if not timescale:
                xmltext = xml.etree.ElementTree.tostring(element)
                if xmltext.count(r'unitName="second"'):
                    timescale = 1
                else:
                    timescale = 60

            if spec['ms level'] == 2.0:
                try:
                    rt = float(spec['scan time']) * timescale
                except:
                    continue

                for p in spec['precursors']:
                    pmz = float(p['mz'])
                    try:
                        pz = int(p['charge'])
                    except:
                        pz = 0

                    featured = False
                    peaks = sorted(filter(lambda x: x[1], spec.centroidedPeaks), key=lambda i: i[0])

                    for f in features:
                        fmz, fz, frt_left, frt_right, frt = f
                        if frt_left < rt < frt_right and abs(pmz - fmz) < iso_width:
                            if abs(pmz - fmz) / pmz <= MS1_Precision: 
                                featured = True
                            print 'BEGIN IONS'
                            print 'TITLE=%d[%d:%f:%f]' % (idx, features.index(f), fmz, frt)
                            print 'RTINSECONDS=%f' % rt
                            print 'PEPMASS=%f' % (fmz - fmz * dm_offset * 1e-6)
                            print 'CHARGE=%d+' % fz
                            print 'RAWFILE=%s [%f:%d] diff:%f' % (title, pmz, pz, (fmz - pmz))
                            for a, b in peaks:
                                print a, b
                            print 'END IONS\n'

                    if featured == False and pz > 1:
                        print 'BEGIN IONS'
                        print 'TITLE=%d[-:%f:%f]' % (idx, pmz, rt)
                        print 'RTINSECONDS=%f' % rt
                        print 'PEPMASS=%f' % (pmz - pmz * dm_offset * 1e-6)
                        print 'CHARGE=%d+' % pz
                        print 'RAWFILE=%s' % (title)
                        for a, b in peaks:
                            print a, b
                        print 'END IONS\n'
    except KeyError:
        pass    
    return outpath


if __name__ == '__main__':

    feature_fn = sys.argv[1]    # feature csv table exported from FeatureXML by TOPP. 
    mzml_fn = sys.argv[2]       # centroided MS/MS spectra in mzML, the same file which has been used in the first-pass database search.
    rawpsm_fn = sys.argv[3]     # first-pass database search result: Morpheus .PSMs.tsv file. 
    full_iso_width = float(sys.argv[4]) # the total width of precursor isolation window.

    psm = load_PSM(rawpsm_fn)
    # spectra_clone(feature_fn, mzml_fn, full_iso_width)

    macc = psm['PrecursorError(ppm)']
    sys.stderr.write("Mean Mass Error (ppm): %.3f SD: %.3f\n" % (macc.mean(), macc.std()))

